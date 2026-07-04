import tarfile
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import duckdb

from backend.app.db import get_connection, initialize_database
from backend.app.repositories import (
    claim_transcription_job,
    create_job,
    create_rss_episode,
    get_or_create_speaker_by_name,
    now_utc,
)
from backend.app.services.backups import create_database_backup
from backend.app.services.rss_import import classify_episode, ensure_transcription_job, parse_feed
from backend.app.storage import LocalObjectStorage, R2ObjectStorage


RSS_FIXTURE = b"""<?xml version="1.0"?>
<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" version="2.0">
  <channel>
    <item><title>Episode 001 - Chocolate</title><guid>main-1</guid>
      <pubDate>Wed, 04 Jan 2023 21:30:06 GMT</pubDate>
      <description>Main episode</description><itunes:episode>1</itunes:episode>
      <itunes:duration>01:02:03</itunes:duration>
      <enclosure url="https://example.com/main.mp3" length="100" type="audio/mpeg" />
    </item>
    <item><title>Mini Episode 001 - JFK</title><guid>mini-1</guid>
      <pubDate>Thu, 06 Jul 2023 05:21:28 GMT</pubDate>
      <itunes:episode>1</itunes:episode><itunes:duration>10:00</itunes:duration>
      <enclosure url="https://example.com/mini.mp3" length="20" type="audio/mpeg" />
    </item>
    <item><title>Are You On A Break?</title><guid>break</guid>
      <pubDate>Thu, 01 Jan 2026 00:00:00 GMT</pubDate>
      <enclosure url="https://example.com/break.mp3" length="10" type="audio/mpeg" />
    </item>
  </channel>
</rss>"""


def test_rss_parser_distinguishes_main_mini_and_announcement():
    items = parse_feed(RSS_FIXTURE)

    assert [(item["episode_kind"], item["episode_number"]) for item in items] == [
        ("main", 1),
        ("mini", 1),
        ("announcement", None),
    ]
    assert items[0]["duration_seconds"] == 3723
    assert classify_episode("Something else", None) == ("announcement", None)


def test_rss_guid_is_idempotent_and_announcements_allow_null_number(tmp_path, monkeypatch):
    database = tmp_path / "production.duckdb"
    monkeypatch.setenv("AYQM_DATABASE_PATH", str(database))
    from backend.app.config import get_settings

    get_settings.cache_clear()
    initialize_database(database)
    item = parse_feed(RSS_FIXTURE)[-1] | {"object_key": "episodes/break/source.mp3"}
    with get_connection() as conn:
        speaker = get_or_create_speaker_by_name(conn, "Vineeth Nair")
        first, created = create_rss_episode(conn, item, [speaker["id"]])
        second, created_again = create_rss_episode(conn, item, [speaker["id"]])
        ensure_transcription_job(conn, first)
        ensure_transcription_job(conn, second)
        queued_jobs = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE episode_id = ? AND kind = 'transcribe'",
            [first["id"]],
        ).fetchone()[0]

    assert created is True
    assert created_again is False
    assert first["id"] == second["id"]
    assert first["episode_number"] is None
    assert first["episode_kind"] == "announcement"
    assert queued_jobs == 1
    get_settings.cache_clear()


def test_expired_worker_lease_is_reclaimed(tmp_path, monkeypatch):
    database = tmp_path / "jobs.duckdb"
    monkeypatch.setenv("AYQM_DATABASE_PATH", str(database))
    from backend.app.config import get_settings

    get_settings.cache_clear()
    initialize_database(database)
    item = parse_feed(RSS_FIXTURE)[0] | {"object_key": "episodes/main-1/source.mp3"}
    with get_connection() as conn:
        speaker = get_or_create_speaker_by_name(conn, "Aditya Kashyap")
        episode, _ = create_rss_episode(conn, item, [speaker["id"]])
        job = create_job(conn, episode["id"], "transcribe", {"diarize": True})
        first = claim_transcription_job(conn, "lease-one", 60)
        conn.execute(
            "UPDATE jobs SET lease_expires_at = ? WHERE id = ?",
            [now_utc() - timedelta(seconds=1), job["id"]],
        )
        second = claim_transcription_job(conn, "lease-two", 60)

    assert first["id"] == second["id"]
    assert second["attempts"] == 2
    get_settings.cache_clear()


def test_portable_backup_is_written_to_local_object_storage(tmp_path, monkeypatch):
    database = tmp_path / "database" / "ayqm.duckdb"
    storage_root = tmp_path / "objects"
    monkeypatch.setenv("AYQM_DATABASE_PATH", str(database))
    monkeypatch.setenv("AYQM_UPLOAD_ROOT", str(storage_root))
    from backend.app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    settings.ensure_storage()
    initialize_database(database)

    keys = create_database_backup(settings)

    archive = storage_root / keys[0]
    assert archive.exists()
    with tarfile.open(archive, "r:gz") as backup:
        names = backup.getnames()
        restore_root = tmp_path / "restore"
        backup.extractall(restore_root, filter="data")
    assert "manifest.json" in names
    assert "database/schema.sql" in names
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM backup_records").fetchone()[0] >= 1
    restored = duckdb.connect(str(tmp_path / "restored.duckdb"))
    try:
        export_path = str(restore_root / "database").replace("'", "''")
        restored.execute(f"IMPORT DATABASE '{export_path}'")
        assert restored.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 0
    finally:
        restored.close()
    get_settings.cache_clear()


def test_local_object_storage_deletion_is_idempotent(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    storage.put_json("episodes/episode-1/source.json", {"source": True})
    storage.put_json("artifacts/episode-1/transcript.json", {"segments": []})
    storage.put_json("artifacts/episode-1/trivia.json", {"items": []})

    storage.delete_object("episodes/episode-1/source.json")
    storage.delete_object("episodes/episode-1/source.json")
    storage.delete_prefix("artifacts/episode-1/")
    storage.delete_prefix("artifacts/episode-1/")

    assert not (tmp_path / "episodes/episode-1/source.json").exists()
    assert not (tmp_path / "artifacts/episode-1").exists()


def test_r2_object_storage_deletes_objects_and_batched_prefixes():
    class Paginator:
        def paginate(self, **kwargs):
            assert kwargs == {"Bucket": "test-bucket", "Prefix": "artifacts/episode-1/"}
            return [{"Contents": [{"Key": f"artifact-{index}"} for index in range(1001)]}, {}]

    class Client:
        def __init__(self):
            self.deleted_objects = []
            self.deleted_batches = []

        def delete_object(self, **kwargs):
            self.deleted_objects.append(kwargs)

        def get_paginator(self, operation):
            assert operation == "list_objects_v2"
            return Paginator()

        def delete_objects(self, **kwargs):
            self.deleted_batches.append(kwargs)

    storage = R2ObjectStorage.__new__(R2ObjectStorage)
    storage.client = Client()
    storage.bucket = "test-bucket"

    storage.delete_object("episodes/episode-1/source.mp3")
    storage.delete_prefix("artifacts/episode-1/")

    assert storage.client.deleted_objects == [
        {"Bucket": "test-bucket", "Key": "episodes/episode-1/source.mp3"}
    ]
    assert [len(batch["Delete"]["Objects"]) for batch in storage.client.deleted_batches] == [1000, 1]
    assert all(batch["Delete"]["Quiet"] is True for batch in storage.client.deleted_batches)


def test_api_starts_without_transcription_dependencies(tmp_path):
    script = """
import importlib.abc
import sys

class BlockMlImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == 'ayqm_transcribe' or fullname.startswith(('ayqm_transcribe.', 'whisperx', 'torch')):
            raise ImportError(f'blocked API-only dependency: {fullname}')
        return None

sys.meta_path.insert(0, BlockMlImports())
from backend.app.main import create_app
assert create_app().title == 'AYQM Webapp API'
"""
    environment = os.environ.copy()
    environment.update(
        {
            "AYQM_ENVIRONMENT": "local",
            "AYQM_DATABASE_PATH": str(tmp_path / "api-only.duckdb"),
            "AYQM_UPLOAD_ROOT": str(tmp_path / "uploads"),
            "AYQM_EPISODE_ROOT": str(tmp_path / "episodes"),
        }
    )
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
