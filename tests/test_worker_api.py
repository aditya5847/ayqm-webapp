from datetime import timedelta
from io import BytesIO

from backend.app.db import get_connection
from backend.app.repositories import create_job, create_rss_episode, get_or_create_speaker_by_name, now_utc


class FakeWorkerStorage:
    def __init__(self):
        self.put_requests: list[tuple[str, str, int]] = []

    def presign_get(self, key: str, expires_seconds: int = 3600) -> str:
        return f"https://objects.example/{key}?download=1"

    def presign_put(self, key: str, content_type: str, expires_seconds: int = 3600) -> str:
        self.put_requests.append((key, content_type, expires_seconds))
        return f"https://objects.example/{key}?upload=1"


class FakeApiResponse:
    def __init__(self, payload: bytes):
        self.payload = BytesIO(payload)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self.payload.read()


def test_worker_api_request_identifies_client(monkeypatch):
    from backend.app import worker_cli

    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeApiResponse(b"null")

    monkeypatch.setattr(worker_cli, "urlopen", fake_urlopen)

    worker_cli.api_request("https://api.example.com", "secret", "/worker/jobs/claim", {})

    request, timeout = requests[0]
    assert request.get_header("User-agent") == "AYQM-Worker/1.0 (+https://areyouquizzingme.com)"
    assert request.get_header("Accept") == "application/json"
    assert timeout == 60


def test_worker_requests_transcript_upload_after_transcription(client, monkeypatch):
    from backend.app.config import get_settings
    from backend.app.routes import worker as worker_routes

    settings = get_settings()
    settings.storage_backend = "r2"
    settings.worker_token = "worker-secret"
    settings.worker_lease_seconds = 900
    storage = FakeWorkerStorage()
    monkeypatch.setattr(worker_routes, "get_object_storage", lambda _settings: storage)

    item = {
        "rss_guid": "worker-test",
        "episode_title": "Episode 1 - Worker Test",
        "episode_number": 1,
        "episode_kind": "main",
        "episode_description": None,
        "published_at": None,
        "enclosure_url": "https://podcast.example/episode.mp3",
        "content_type": "audio/mpeg",
        "size_bytes": 123,
        "duration_seconds": 60,
        "extra_metadata": {},
        "object_key": "episodes/worker-test/source.mp3",
    }
    with get_connection() as conn:
        speaker = get_or_create_speaker_by_name(conn, "Test Speaker")
        episode, _ = create_rss_episode(conn, item, [speaker["id"]])
        job = create_job(conn, episode["id"], "transcribe", {"diarize": True})

    headers = {"Authorization": "Bearer worker-secret"}
    claimed = client.post("/worker/jobs/claim", json={"worker_name": "test-worker"}, headers=headers)

    assert claimed.status_code == 200
    lease = claimed.json()
    assert lease["job"]["id"] == job["id"]
    assert "transcript_upload_url" not in lease
    assert storage.put_requests == []

    upload = client.post(
        f"/worker/jobs/{job['id']}/transcript-upload",
        json={"lease_token": lease["lease_token"]},
        headers=headers,
    )

    assert upload.status_code == 200
    assert upload.json() == {
        "transcript_object_key": f"artifacts/{episode['id']}/transcript.json",
        "transcript_upload_url": f"https://objects.example/artifacts/{episode['id']}/transcript.json?upload=1",
        "transcript_upload_headers": {"Content-Type": "application/json"},
    }
    assert storage.put_requests == [
        (f"artifacts/{episode['id']}/transcript.json", "application/json", 900)
    ]

    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET lease_expires_at = ? WHERE id = ?",
            [now_utc() - timedelta(seconds=1), job["id"]],
        )

    expired = client.post(
        f"/worker/jobs/{job['id']}/transcript-upload",
        json={"lease_token": lease["lease_token"]},
        headers=headers,
    )
    assert expired.status_code == 409


def test_worker_exits_after_idle_timeout(monkeypatch):
    import sys

    from backend.app import worker_cli

    clock = [0.0]
    claims = []

    def fake_request(*args, **kwargs):
        claims.append((args, kwargs))
        return None

    monkeypatch.setattr(worker_cli, "api_request", fake_request)
    monkeypatch.setattr(worker_cli.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(worker_cli.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ayqm-worker",
            "--api-url",
            "https://api.example.com",
            "--token",
            "secret",
            "--poll-seconds",
            "2",
            "--idle-timeout-seconds",
            "5",
        ],
    )

    worker_cli.main()

    assert clock[0] == 6
    assert len(claims) == 4
