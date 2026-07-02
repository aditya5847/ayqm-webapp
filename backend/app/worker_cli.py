import argparse
import hashlib
import json
import shutil
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .config import get_settings
from .schemas import TranscriptionRequest
from .services.transcription import run_transcription


def api_request(api_url: str, token: str, path: str, payload: dict | None = None, method: str = "POST"):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{api_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            content = response.read()
            return json.loads(content) if content else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Worker API returned {exc.code}: {detail}") from exc


def heartbeat_loop(api_url: str, token: str, job_id: str, lease_token: str, stop: threading.Event) -> None:
    while not stop.wait(60):
        api_request(
            api_url,
            token,
            f"/worker/jobs/{job_id}/heartbeat",
            {"lease_token": lease_token, "progress": {"stage": "transcribing"}},
        )


def process_lease(api_url: str, token: str, lease: dict, args: argparse.Namespace) -> None:
    job = lease["job"]
    stop = threading.Event()
    heartbeat = threading.Thread(
        target=heartbeat_loop,
        args=(api_url, token, job["id"], lease["lease_token"], stop),
        daemon=True,
    )
    heartbeat.start()
    try:
        with TemporaryDirectory(prefix=f"ayqm-worker-{job['episode_id']}-") as temporary:
            root = Path(temporary)
            audio_path = root / "source.mp3"
            with urlopen(lease["audio_url"], timeout=300) as response, audio_path.open("wb") as output:
                shutil.copyfileobj(response, output)
            transcription = TranscriptionRequest.model_validate(lease["transcription"])
            transcription = transcription.model_copy(
                update={
                    "model_name": args.model,
                    "device": args.device,
                    "compute_type": args.compute_type,
                    "batch_size": args.batch_size,
                    "hf_token": args.hf_token or transcription.hf_token,
                }
            )
            transcript, transcript_path = run_transcription(audio_path, root, transcription, get_settings())
            if not transcript_path.exists():
                transcript_path.write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
            payload = transcript_path.read_bytes()
            upload = Request(
                lease["transcript_upload_url"],
                data=payload,
                method="PUT",
                headers=lease["transcript_upload_headers"],
            )
            with urlopen(upload, timeout=300):
                pass
            api_request(
                api_url,
                token,
                f"/worker/jobs/{job['id']}/complete",
                {
                    "lease_token": lease["lease_token"],
                    "transcript_object_key": lease["transcript_object_key"],
                    "transcript_sha256": hashlib.sha256(payload).hexdigest(),
                },
            )
    except Exception as exc:
        api_request(
            api_url,
            token,
            f"/worker/jobs/{job['id']}/fail",
            {"lease_token": lease["lease_token"], "error": str(exc)},
        )
        raise
    finally:
        stop.set()
        heartbeat.join(timeout=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process AYQM transcription jobs from a trusted machine.")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--worker-name", default="ayqm-local-worker")
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--hf-token")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()

    while True:
        lease = api_request(
            args.api_url,
            args.token,
            "/worker/jobs/claim",
            {"worker_name": args.worker_name},
        )
        if lease is None:
            if args.once:
                return
            time.sleep(args.poll_seconds)
            continue
        process_lease(args.api_url, args.token, lease, args)
        if args.once:
            return


if __name__ == "__main__":
    main()
