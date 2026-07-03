import hmac
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, status

from ..config import get_settings
from ..db import get_connection
from ..repositories import (
    claim_transcription_job,
    get_episode,
    get_job,
    save_transcript,
    update_job_progress,
    update_job_status,
    worker_lease_matches,
)
from ..schemas import (
    TranscriptionRequest,
    WorkerComplete,
    WorkerFailure,
    WorkerHeartbeat,
    WorkerJobClaim,
    WorkerJobLease,
    WorkerTranscriptUpload,
    WorkerUploadRequest,
)
from ..storage import get_object_storage


router = APIRouter(prefix="/worker", tags=["worker"], include_in_schema=False)


def require_worker(authorization: str | None = Header(default=None)) -> None:
    configured = get_settings().worker_token
    if not configured:
        raise HTTPException(status_code=503, detail="Worker authentication is not configured")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not hmac.compare_digest(configured, supplied):
        raise HTTPException(status_code=401, detail="Invalid worker token")


@router.post("/jobs/claim", response_model=WorkerJobLease | None, dependencies=[])
def claim_job(request: WorkerJobClaim, authorization: str | None = Header(default=None)) -> dict | None:
    require_worker(authorization)
    settings = get_settings()
    if settings.storage_backend != "r2":
        raise HTTPException(status_code=409, detail="External workers require R2 object storage")
    lease_token = str(uuid4())
    with get_connection() as conn:
        job = claim_transcription_job(conn, lease_token, settings.worker_lease_seconds)
        if job is None:
            return None
        episode = get_episode(conn, job["episode_id"])
    if episode is None or not episode.get("audio_object_key"):
        with get_connection() as conn:
            update_job_status(conn, job["id"], "failed", "Episode has no object-stored audio")
        raise HTTPException(status_code=409, detail="Claimed episode has no object-stored audio")
    storage = get_object_storage(settings)
    audio_url = storage.presign_get(episode["audio_object_key"], expires_seconds=settings.worker_lease_seconds)
    if not audio_url:
        raise HTTPException(status_code=500, detail="Could not issue worker audio URL")
    payload = job.get("payload") or {}
    return {
        "job": job,
        "lease_token": lease_token,
        "audio_url": audio_url,
        "audio_content_type": episode.get("audio_content_type"),
        "transcription": TranscriptionRequest.model_validate(payload),
    }


@router.post("/jobs/{job_id}/transcript-upload", response_model=WorkerTranscriptUpload)
def create_transcript_upload(
    job_id: str,
    request: WorkerUploadRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    require_worker(authorization)
    settings = get_settings()
    with get_connection() as conn:
        job = get_job(conn, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if not worker_lease_matches(conn, job_id, request.lease_token):
            raise HTTPException(status_code=409, detail="Worker lease is no longer valid")
    transcript_key = f"artifacts/{job['episode_id']}/transcript.json"
    transcript_url = get_object_storage(settings).presign_put(
        transcript_key,
        "application/json",
        expires_seconds=settings.worker_lease_seconds,
    )
    if not transcript_url:
        raise HTTPException(status_code=500, detail="Could not issue worker transcript upload URL")
    return {
        "transcript_object_key": transcript_key,
        "transcript_upload_url": transcript_url,
        "transcript_upload_headers": {"Content-Type": "application/json"},
    }


@router.post("/jobs/{job_id}/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def heartbeat_job(job_id: str, request: WorkerHeartbeat, authorization: str | None = Header(default=None)) -> None:
    require_worker(authorization)
    settings = get_settings()
    with get_connection() as conn:
        updated = update_job_progress(
            conn,
            job_id,
            request.lease_token,
            request.progress.stage,
            request.progress.current,
            request.progress.total,
            settings.worker_lease_seconds,
        )
    if not updated:
        raise HTTPException(status_code=409, detail="Worker lease is no longer valid")


@router.post("/jobs/{job_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
def complete_job(job_id: str, request: WorkerComplete, authorization: str | None = Header(default=None)) -> None:
    require_worker(authorization)
    settings = get_settings()
    with get_connection() as conn:
        job = get_job(conn, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if not worker_lease_matches(conn, job_id, request.lease_token):
            raise HTTPException(status_code=409, detail="Worker lease is no longer valid")
    expected_key = f"artifacts/{job['episode_id']}/transcript.json"
    if request.transcript_object_key != expected_key:
        raise HTTPException(status_code=422, detail="Unexpected transcript object key")
    storage = get_object_storage(settings)
    if storage.head(expected_key) is None:
        raise HTTPException(status_code=409, detail="Transcript artifact has not been uploaded")
    transcript = storage.read_json(expected_key)
    if not isinstance(transcript.get("segments"), list):
        raise HTTPException(status_code=422, detail="Transcript artifact has no segments array")
    with get_connection() as conn:
        if not worker_lease_matches(conn, job_id, request.lease_token):
            raise HTTPException(status_code=409, detail="Worker lease is no longer valid")
        save_transcript(conn, job["episode_id"], expected_key, transcript)
        conn.execute(
            "UPDATE jobs SET artifact_key = ?, artifact_sha256 = ? WHERE id = ?",
            [expected_key, request.transcript_sha256, job_id],
        )
        update_job_status(conn, job_id, "succeeded")


@router.post("/jobs/{job_id}/fail", status_code=status.HTTP_204_NO_CONTENT)
def fail_job(job_id: str, request: WorkerFailure, authorization: str | None = Header(default=None)) -> None:
    require_worker(authorization)
    with get_connection() as conn:
        if not worker_lease_matches(conn, job_id, request.lease_token):
            raise HTTPException(status_code=409, detail="Worker lease is no longer valid")
        update_job_status(conn, job_id, "failed", request.error)
