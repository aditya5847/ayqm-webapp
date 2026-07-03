import argparse
import hashlib
import json
import logging
import os
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

logger = logging.getLogger("ayqm.worker")


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
        try:
            api_request(
                api_url,
                token,
                f"/worker/jobs/{job_id}/heartbeat",
                {"lease_token": lease_token, "progress": {"stage": "transcribing"}},
            )
        except Exception:
            logger.exception("Heartbeat failed for job %s", job_id)


def process_lease(api_url: str, token: str, lease: dict, args: argparse.Namespace) -> None:
    job = lease["job"]
    logger.info("Claimed job %s for episode %s", job["id"], job["episode_id"])
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
            logger.info("Downloading audio for job %s", job["id"])
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
            logger.info(
                "Starting transcription for job %s with model=%s device=%s compute_type=%s",
                job["id"],
                transcription.model_name,
                transcription.device,
                transcription.compute_type,
            )
            transcript, transcript_path = run_transcription(audio_path, root, transcription, get_settings())
            if not transcript_path.exists():
                transcript_path.write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
            payload = transcript_path.read_bytes()
            upload_lease = api_request(
                api_url,
                token,
                f"/worker/jobs/{job['id']}/transcript-upload",
                {"lease_token": lease["lease_token"]},
            )
            upload = Request(
                upload_lease["transcript_upload_url"],
                data=payload,
                method="PUT",
                headers=upload_lease["transcript_upload_headers"],
            )
            with urlopen(upload, timeout=300):
                pass
            logger.info("Uploaded transcript for job %s", job["id"])
            api_request(
                api_url,
                token,
                f"/worker/jobs/{job['id']}/complete",
                {
                    "lease_token": lease["lease_token"],
                    "transcript_object_key": upload_lease["transcript_object_key"],
                    "transcript_sha256": hashlib.sha256(payload).hexdigest(),
                },
            )
            logger.info("Completed job %s", job["id"])
    except Exception as exc:
        logger.exception("Job %s failed", job["id"])
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
    logging.basicConfig(
        level=os.getenv("AYQM_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Process AYQM transcription jobs from a trusted machine.")
    parser.add_argument("--api-url", default=os.getenv("AYQM_API_URL"))
    parser.add_argument("--token", default=os.getenv("AYQM_WORKER_TOKEN"))
    parser.add_argument("--worker-name", default="ayqm-local-worker")
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--hf-token", default=os.getenv("HF_TOKEN"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-jobs", type=int)
    parser.add_argument("--idle-timeout-seconds", type=int)
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()
    if not args.api_url:
        parser.error("--api-url or AYQM_API_URL is required")
    if not args.token:
        parser.error("--token or AYQM_WORKER_TOKEN is required")
    if args.max_jobs is not None and args.max_jobs < 1:
        parser.error("--max-jobs must be at least 1")
    if args.idle_timeout_seconds is not None and args.idle_timeout_seconds < 1:
        parser.error("--idle-timeout-seconds must be at least 1")
    if args.poll_seconds < 1:
        parser.error("--poll-seconds must be at least 1")

    completed_jobs = 0
    idle_started_at = time.monotonic()
    logger.info("Worker %s is polling %s", args.worker_name, args.api_url)
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
            idle_seconds = time.monotonic() - idle_started_at
            if args.idle_timeout_seconds is not None and idle_seconds >= args.idle_timeout_seconds:
                logger.info("Worker stopping after %s idle seconds", round(idle_seconds))
                return
            logger.info("No transcription jobs available; polling again in %s seconds", args.poll_seconds)
            time.sleep(args.poll_seconds)
            continue
        process_lease(args.api_url, args.token, lease, args)
        idle_started_at = time.monotonic()
        completed_jobs += 1
        if args.once or (args.max_jobs is not None and completed_jobs >= args.max_jobs):
            logger.info("Worker stopping after %s completed job(s)", completed_jobs)
            return


if __name__ == "__main__":
    main()
