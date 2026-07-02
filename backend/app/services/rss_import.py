import hashlib
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import PurePosixPath
from threading import Thread
from typing import BinaryIO
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4
from xml.etree import ElementTree

from ..config import Settings
from ..db import get_connection
from ..repositories import (
    create_job,
    create_rss_episode,
    get_or_create_speaker_by_name,
    now_utc,
)
from ..storage import get_object_storage


ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
HOST_NAMES = ("Vineeth Nair", "Aditya Kashyap")


class HashingReader:
    def __init__(self, source: BinaryIO):
        self.source = source
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self.source.read(size)
        if chunk:
            self.digest.update(chunk)
            self.size += len(chunk)
        return chunk

    @property
    def sha256(self) -> str:
        return self.digest.hexdigest()


def parse_duration(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        parts = [float(part) for part in raw.strip().split(":")]
    except ValueError:
        return None
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


def classify_episode(title: str, itunes_number: str | None) -> tuple[str, int | None]:
    mini = re.search(r"\bMini Episode\s+(\d+)", title, re.IGNORECASE)
    if mini:
        return "mini", int(mini.group(1))
    main = re.search(r"\bEpisode\s+(\d+)", title, re.IGNORECASE)
    if main:
        return "main", int(main.group(1))
    if itunes_number and itunes_number.isdigit():
        return "main", int(itunes_number)
    return "announcement", None


def parse_feed(payload: bytes) -> list[dict]:
    root = ElementTree.fromstring(payload)
    items: list[dict] = []
    for node in root.findall("./channel/item"):
        title = (node.findtext("title") or "Untitled episode").strip()
        guid = (node.findtext("guid") or "").strip()
        enclosure = node.find("enclosure")
        enclosure_url = enclosure.get("url", "").strip() if enclosure is not None else ""
        if not guid or not enclosure_url:
            continue
        kind, number = classify_episode(title, node.findtext(f"{{{ITUNES_NS}}}episode"))
        published_raw = node.findtext("pubDate")
        published_at = parsedate_to_datetime(published_raw).astimezone(UTC).replace(tzinfo=None) if published_raw else None
        size = enclosure.get("length") if enclosure is not None else None
        items.append(
            {
                "rss_guid": guid,
                "episode_title": title,
                "episode_number": number,
                "episode_kind": kind,
                "episode_description": (node.findtext("description") or "").strip() or None,
                "published_at": published_at,
                "enclosure_url": enclosure_url,
                "content_type": enclosure.get("type") if enclosure is not None else None,
                "size_bytes": int(size) if size and size.isdigit() else None,
                "duration_seconds": parse_duration(node.findtext(f"{{{ITUNES_NS}}}duration")),
                "extra_metadata": {"rss_guid": guid, "episode_kind": kind},
            }
        )
    return sorted(items, key=lambda item: item["published_at"] or datetime.min)


def fetch_feed(feed_url: str) -> list[dict]:
    request = Request(
        feed_url,
        headers={"User-Agent": "AYQM-Webapp/1.0 (+https://github.com/aditya5847/ayqm-webapp)"},
    )
    with urlopen(request, timeout=60) as response:
        return parse_feed(response.read())


def audio_object_key(item: dict) -> str:
    suffix = PurePosixPath(urlparse(item["enclosure_url"]).path).suffix.lower()
    if not suffix or len(suffix) > 8:
        suffix = ".mp3"
    safe_guid = re.sub(r"[^A-Za-z0-9._-]", "-", item["rss_guid"])
    return f"episodes/{safe_guid}/source{suffix}"


def create_feed_import(feed_url: str, dry_run: bool) -> dict:
    import_id = str(uuid4())
    timestamp = now_utc()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO feed_imports (
                id, feed_url, status, dry_run, discovered_count, imported_count,
                skipped_count, failed_count, error, created_at, started_at, finished_at
            ) VALUES (?, ?, 'queued', ?, 0, 0, 0, 0, NULL, ?, NULL, NULL)
            """,
            [import_id, feed_url, dry_run, timestamp],
        )
        return get_feed_import(conn, import_id)


def get_feed_import(conn, import_id: str) -> dict | None:
    row = conn.execute(
        """
        SELECT id, feed_url, status, dry_run, discovered_count, imported_count,
               skipped_count, failed_count, error, created_at, started_at, finished_at
        FROM feed_imports WHERE id = ?
        """,
        [import_id],
    ).fetchone()
    if row is None:
        return None
    keys = (
        "id", "feed_url", "status", "dry_run", "discovered_count", "imported_count",
        "skipped_count", "failed_count", "error", "created_at", "started_at", "finished_at",
    )
    return dict(zip(keys, row, strict=True))


def ensure_transcription_job(conn, episode: dict) -> None:
    active = conn.execute(
        """
        SELECT COUNT(*) FROM jobs
        WHERE episode_id = ? AND kind = 'transcribe'
          AND status IN ('queued', 'running')
        """,
        [episode["id"]],
    ).fetchone()[0]
    if episode["transcript_status"] == "missing" and not active:
        create_job(conn, episode["id"], "transcribe", {"diarize": True})


def run_feed_import(import_id: str, settings: Settings) -> None:
    storage = get_object_storage(settings)
    started = now_utc()
    with get_connection() as conn:
        record = get_feed_import(conn, import_id)
        if record is None:
            return
        conn.execute(
            "UPDATE feed_imports SET status = 'running', started_at = ?, error = NULL WHERE id = ?",
            [started, import_id],
        )
    try:
        items = fetch_feed(record["feed_url"])
        with get_connection() as conn:
            conn.execute("UPDATE feed_imports SET discovered_count = ? WHERE id = ?", [len(items), import_id])
        if record["dry_run"]:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE feed_imports SET status = 'succeeded', finished_at = ? WHERE id = ?",
                    [now_utc(), import_id],
                )
            return

        with get_connection() as conn:
            host_ids = [get_or_create_speaker_by_name(conn, name)["id"] for name in HOST_NAMES]

        imported = skipped = failed = 0
        for item in items:
            try:
                key = audio_object_key(item)
                item["object_key"] = key
                object_metadata = storage.head(key)
                if object_metadata is None:
                    request = Request(
                        item["enclosure_url"],
                        headers={"User-Agent": "AYQM-Webapp/1.0 (+https://github.com/aditya5847/ayqm-webapp)"},
                    )
                    with urlopen(request, timeout=300) as response:
                        reader = HashingReader(response)
                        stored = storage.put_stream(key, reader, item.get("content_type"))
                        item["size_bytes"] = stored.get("size") or reader.size
                        item["audio_sha256"] = stored.get("sha256") or reader.sha256
                else:
                    item["size_bytes"] = object_metadata.get("size") or item.get("size_bytes")
                with get_connection() as conn:
                    episode, created = create_rss_episode(conn, item, host_ids)
                    if item.get("audio_sha256"):
                        conn.execute(
                            "UPDATE episodes SET audio_sha256 = ? WHERE id = ?",
                            [item["audio_sha256"], episode["id"]],
                        )
                    ensure_transcription_job(conn, episode)
                    if created:
                        imported += 1
                    else:
                        skipped += 1
                    conn.execute(
                        """
                        UPDATE feed_imports SET imported_count = ?, skipped_count = ?, failed_count = ?
                        WHERE id = ?
                        """,
                        [imported, skipped, failed, import_id],
                    )
            except Exception:
                failed += 1
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE feed_imports SET failed_count = ? WHERE id = ?",
                        [failed, import_id],
                    )
        final_status = "succeeded" if failed == 0 else "failed"
        final_error = None if failed == 0 else f"{failed} feed items failed; rerun is safe"
        with get_connection() as conn:
            conn.execute(
                "UPDATE feed_imports SET status = ?, error = ?, finished_at = ? WHERE id = ?",
                [final_status, final_error, now_utc(), import_id],
            )
    except Exception as exc:
        with get_connection() as conn:
            conn.execute(
                "UPDATE feed_imports SET status = 'failed', error = ?, finished_at = ? WHERE id = ?",
                [str(exc), now_utc(), import_id],
            )


def resume_pending_feed_imports(settings: Settings) -> None:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM feed_imports WHERE status IN ('queued', 'running') ORDER BY created_at"
        ).fetchall()
    for (import_id,) in rows:
        Thread(target=run_feed_import, args=(import_id, settings), daemon=True).start()
