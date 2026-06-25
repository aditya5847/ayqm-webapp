import json
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError

from ..config import get_settings
from ..db import get_connection
from ..repositories import (
    create_episode,
    create_job,
    get_episode,
    get_speaker_mapping,
    get_transcript,
    list_episodes,
    list_trivia_items,
    missing_speaker_ids,
    replace_speaker_mapping,
    speaker_ids_for_episode,
)
from ..schemas import (
    EpisodeMetadata,
    EpisodeOut,
    JobAccepted,
    ProcessRequest,
    SpeakerMappingIn,
    SpeakerMappingOut,
    TranscriptOut,
    TranscriptionRequest,
    TriviaExtractionRequest,
    TriviaItemOut,
)
from ..workers import extract_trivia_job, process_episode_job, transcribe_episode_job

router = APIRouter(prefix="/episodes", tags=["episodes"])


def _parse_json_field(raw_value: str, field_name: str) -> object:
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be valid JSON") from exc


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_metadata(
    episode_title: str,
    episode_number: int,
    episode_description: str | None,
    published_at: str | None,
    source_url: str | None,
    speaker_ids: str,
    extra_metadata: str | None,
) -> EpisodeMetadata:
    payload = {
        "episode_title": episode_title,
        "episode_number": episode_number,
        "episode_description": _blank_to_none(episode_description),
        "published_at": _blank_to_none(published_at),
        "source_url": _blank_to_none(source_url),
        "speaker_ids": _parse_json_field(speaker_ids, "speaker_ids"),
        "extra_metadata": _parse_json_field(extra_metadata, "extra_metadata") if _blank_to_none(extra_metadata) else {},
    }
    try:
        return EpisodeMetadata.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _require_episode(episode_id: str) -> dict:
    with get_connection() as conn:
        episode = get_episode(conn, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.post("", response_model=EpisodeOut, status_code=status.HTTP_201_CREATED)
def upload_episode(
    audio_file: UploadFile = File(..., alias="file"),
    episode_title: str = Form(...),
    episode_number: int = Form(...),
    speaker_ids: str = Form(...),
    episode_description: str | None = Form(default=None),
    published_at: str | None = Form(default=None),
    source_url: str | None = Form(default=None),
    extra_metadata: str | None = Form(default=None),
) -> dict:
    settings = get_settings()
    settings.ensure_storage()
    parsed_metadata = _parse_metadata(
        episode_title=episode_title,
        episode_number=episode_number,
        episode_description=episode_description,
        published_at=published_at,
        source_url=source_url,
        speaker_ids=speaker_ids,
        extra_metadata=extra_metadata,
    )

    with get_connection() as conn:
        missing = missing_speaker_ids(conn, parsed_metadata.speaker_ids)
        if missing:
            raise HTTPException(status_code=422, detail={"unknown_speaker_ids": missing})
        if len(set(parsed_metadata.speaker_ids)) != len(parsed_metadata.speaker_ids):
            raise HTTPException(status_code=422, detail="speaker_ids must not contain duplicates")
        episode = create_episode(
            conn,
            parsed_metadata,
            audio_path="pending",
            audio_content_type=audio_file.content_type,
        )

    suffix = Path(audio_file.filename or "audio").suffix or ".audio"
    upload_dir = settings.upload_root / episode["id"]
    upload_dir.mkdir(parents=True, exist_ok=True)
    audio_path = upload_dir / f"original{suffix}"
    with audio_path.open("wb") as output:
        shutil.copyfileobj(audio_file.file, output)

    with get_connection() as conn:
        conn.execute(
            "UPDATE episodes SET audio_path = ?, updated_at = current_timestamp WHERE id = ?",
            [str(audio_path), episode["id"]],
        )
        updated = get_episode(conn, episode["id"])
    return updated


@router.get("", response_model=list[EpisodeOut])
def get_episodes() -> list[dict]:
    with get_connection() as conn:
        return list_episodes(conn)


@router.get("/{episode_id}", response_model=EpisodeOut)
def get_episode_detail(episode_id: str) -> dict:
    return _require_episode(episode_id)


@router.post("/{episode_id}/transcribe", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
def start_transcription(
    episode_id: str,
    background_tasks: BackgroundTasks,
    request: TranscriptionRequest | None = None,
) -> dict:
    _require_episode(episode_id)
    payload = request or TranscriptionRequest()
    settings = get_settings()
    with get_connection() as conn:
        job = create_job(conn, episode_id, "transcribe")
    background_tasks.add_task(transcribe_episode_job, job["id"], episode_id, payload, settings)
    return {"job_id": job["id"], "episode_id": episode_id, "status": "queued"}


@router.post("/{episode_id}/extract-trivia", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
def start_trivia_extraction(
    episode_id: str,
    background_tasks: BackgroundTasks,
    request: TriviaExtractionRequest | None = None,
) -> dict:
    _require_episode(episode_id)
    with get_connection() as conn:
        if get_transcript(conn, episode_id) is None:
            raise HTTPException(status_code=409, detail="Episode has no transcript yet")
        job = create_job(conn, episode_id, "extract_trivia")
    payload = request or TriviaExtractionRequest()
    settings = get_settings()
    background_tasks.add_task(extract_trivia_job, job["id"], episode_id, payload, settings)
    return {"job_id": job["id"], "episode_id": episode_id, "status": "queued"}


@router.post("/{episode_id}/process", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
def start_processing(
    episode_id: str,
    background_tasks: BackgroundTasks,
    request: ProcessRequest | None = None,
) -> dict:
    _require_episode(episode_id)
    payload = request or ProcessRequest()
    settings = get_settings()
    with get_connection() as conn:
        job = create_job(conn, episode_id, "process")
    background_tasks.add_task(process_episode_job, job["id"], episode_id, payload, settings)
    return {"job_id": job["id"], "episode_id": episode_id, "status": "queued"}


@router.get("/{episode_id}/transcript", response_model=TranscriptOut)
def read_transcript(episode_id: str) -> dict:
    _require_episode(episode_id)
    with get_connection() as conn:
        transcript = get_transcript(conn, episode_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return {"episode_id": episode_id, "transcript": transcript}


@router.get("/{episode_id}/trivia", response_model=list[TriviaItemOut])
def read_trivia(episode_id: str) -> list[dict]:
    _require_episode(episode_id)
    with get_connection() as conn:
        return list_trivia_items(conn, episode_id)


@router.get("/{episode_id}/speaker-mapping", response_model=SpeakerMappingOut)
def read_speaker_mapping(episode_id: str) -> dict:
    _require_episode(episode_id)
    with get_connection() as conn:
        return {"episode_id": episode_id, "mappings": get_speaker_mapping(conn, episode_id)}


@router.put("/{episode_id}/speaker-mapping", response_model=SpeakerMappingOut)
def update_speaker_mapping(episode_id: str, request: SpeakerMappingIn) -> dict:
    _require_episode(episode_id)
    with get_connection() as conn:
        allowed_speaker_ids = set(speaker_ids_for_episode(conn, episode_id))
        invalid_speaker_ids = sorted(set(request.mappings.values()) - allowed_speaker_ids)
        if invalid_speaker_ids:
            raise HTTPException(
                status_code=422,
                detail={"speaker_ids_not_selected_for_episode": invalid_speaker_ids},
            )
        mappings = replace_speaker_mapping(conn, episode_id, request.mappings)
    return {"episode_id": episode_id, "mappings": mappings}
