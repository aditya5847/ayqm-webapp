import json
import os
import shutil
import re
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError

from ..config import get_settings
from ..auth import require_admin
from ..db import get_connection
from ..repositories import (
    create_episode,
    create_job,
    delete_episode,
    episode_artifact_keys,
    get_episode,
    get_speaker_mapping,
    get_transcript,
    list_episodes_page,
    list_trivia_items,
    missing_speaker_ids,
    replace_speaker_mapping,
    set_episode_audio,
    set_episode_published,
    speaker_ids_for_episode,
    update_episode,
)
from ..schemas import (
    EpisodeMetadata,
    EpisodePageOut,
    EpisodeOut,
    EpisodePublicationUpdate,
    EpisodeUpdate,
    DirectUploadComplete,
    DirectUploadCreate,
    DirectUploadTicket,
    JobAccepted,
    ProcessRequest,
    SpeakerLabelsOut,
    SpeakerMappingIn,
    SpeakerMappingOut,
    TranscriptOut,
    TranscriptionRequest,
    TriviaExtractionRequest,
    TriviaItemOut,
)
from ..services.speaker_labels import ensure_sample_clip, sanitize_label, speaker_labels_from_transcript, summarize_speaker_labels
from ..services.artwork import episode_artwork_response
from ..workers import extract_trivia_job, process_episode_job, transcribe_episode_job
from ..storage import get_object_storage

router = APIRouter(prefix="/episodes", tags=["episodes"], dependencies=[Depends(require_admin)])


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


def _has_hf_token(request: TranscriptionRequest) -> bool:
    return bool(request.hf_token or os.environ.get("HF_TOKEN"))


def _validate_transcription_request(request: TranscriptionRequest) -> None:
    if request.diarize and not _has_hf_token(request) and not get_settings().external_transcription_worker:
        raise HTTPException(status_code=422, detail="HF_TOKEN is required for diarization")


def _local_audio_path(episode_id: str, episode: dict, settings) -> str:
    object_key = episode.get("audio_object_key")
    if not object_key:
        return episode["audio_path"]
    suffix = Path(object_key).suffix or ".audio"
    cached = settings.episode_root / episode_id / "audio_cache" / f"source{suffix}"
    if not cached.exists():
        get_object_storage(settings).download_file(object_key, cached)
    return str(cached)


def _speaker_label_summary(episode_id: str, episode: dict, transcript: dict, settings) -> list[dict]:
    labels = summarize_speaker_labels(transcript)
    sample_dir = settings.episode_root / episode_id / "speaker_samples"
    for label in labels:
        for index, sample in enumerate(label["samples"]):
            ensure_sample_clip(
                ffmpeg_path=settings.ffmpeg_path,
                audio_path=_local_audio_path(episode_id, episode, settings),
                output_dir=sample_dir,
                label=label["label"],
                start=sample["start"],
                end=sample["end"],
                sample_index=index,
            )
            sample["sample_clip_url"] = f"/episodes/{episode_id}/speaker-labels/{label['label']}/samples/{index}"
        if label["samples"]:
            first = label["samples"][0]
            ensure_sample_clip(
                ffmpeg_path=settings.ffmpeg_path,
                audio_path=_local_audio_path(episode_id, episode, settings),
                output_dir=sample_dir,
                label=label["label"],
                start=first["start"],
                end=first["end"],
            )
        label["sample_clip_url"] = f"/episodes/{episode_id}/speaker-labels/{label['label']}/sample"
    return labels


def _detected_speaker_labels(transcript: dict) -> set[str]:
    return set(speaker_labels_from_transcript(transcript))


def _require_complete_speaker_mapping(conn, episode_id: str, transcript: dict) -> None:
    labels = _detected_speaker_labels(transcript)
    if not labels:
        raise HTTPException(
            status_code=409,
            detail="Transcript has no speaker labels. Re-transcribe with diarization before extracting trivia.",
        )
    mapped_labels = set(get_speaker_mapping(conn, episode_id))
    missing_labels = sorted(labels - mapped_labels)
    if missing_labels:
        raise HTTPException(status_code=409, detail={"unmapped_speaker_labels": missing_labels})


def _require_idle_episode(episode: dict) -> None:
    if episode.get("active_job"):
        raise HTTPException(status_code=409, detail="Episode has an active processing job")


def _remove_episode_directory(root: Path, episode_id: str) -> None:
    root = root.resolve()
    path = (root / episode_id).resolve()
    if root not in path.parents:
        raise ValueError("Episode directory escapes configured storage root")
    if path.exists():
        shutil.rmtree(path)


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


@router.post("/uploads", response_model=DirectUploadTicket, status_code=status.HTTP_201_CREATED)
def initialize_direct_upload(request: DirectUploadCreate) -> dict:
    settings = get_settings()
    if settings.storage_backend != "r2":
        raise HTTPException(status_code=409, detail="Direct uploads require R2 object storage")
    with get_connection() as conn:
        missing = missing_speaker_ids(conn, request.speaker_ids)
        if missing:
            raise HTTPException(status_code=422, detail={"unknown_speaker_ids": missing})
        metadata = EpisodeMetadata.model_validate(request.model_dump(exclude={"file_name", "content_type"}))
        episode = create_episode(conn, metadata, audio_path="pending", audio_content_type=request.content_type)
    suffix = Path(request.file_name).suffix.lower() or ".audio"
    suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,7}", suffix) else ".audio"
    object_key = f"episodes/{episode['id']}/source{suffix}"
    storage = get_object_storage(settings)
    upload_url = storage.presign_put(object_key, request.content_type, expires_seconds=3600)
    if not upload_url:
        raise HTTPException(status_code=500, detail="Could not create direct upload URL")
    with get_connection() as conn:
        set_episode_audio(
            conn,
            episode["id"],
            audio_path=object_key,
            object_key=object_key,
            content_type=request.content_type,
        )
    return {
        "episode_id": episode["id"],
        "object_key": object_key,
        "upload_url": upload_url,
        "required_headers": {"Content-Type": request.content_type},
    }


@router.post("/{episode_id}/uploads/complete", response_model=EpisodeOut)
def complete_direct_upload(episode_id: str, request: DirectUploadComplete) -> dict:
    settings = get_settings()
    episode = _require_episode(episode_id)
    object_key = episode.get("audio_object_key")
    if not object_key:
        raise HTTPException(status_code=409, detail="Episode has no pending object upload")
    metadata = get_object_storage(settings).head(object_key)
    if metadata is None:
        raise HTTPException(status_code=409, detail="Uploaded object was not found")
    with get_connection() as conn:
        updated = set_episode_audio(
            conn,
            episode_id,
            audio_path=object_key,
            object_key=object_key,
            content_type=metadata.get("content_type") or episode.get("audio_content_type"),
            size_bytes=metadata.get("size"),
            sha256=request.sha256,
        )
    return updated


@router.get("", response_model=EpisodePageOut)
def get_episodes(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> dict:
    with get_connection() as conn:
        return list_episodes_page(conn, page=page, page_size=page_size)


@router.get("/{episode_id}", response_model=EpisodeOut)
def get_episode_detail(episode_id: str) -> dict:
    return _require_episode(episode_id)


@router.get("/{episode_id}/artwork", response_model=None)
def get_episode_artwork(episode_id: str):
    return episode_artwork_response(_require_episode(episode_id), get_settings())


@router.patch("/{episode_id}", response_model=EpisodeOut)
def update_episode_detail(episode_id: str, request: EpisodeUpdate) -> dict:
    with get_connection() as conn:
        if get_episode(conn, episode_id) is None:
            raise HTTPException(status_code=404, detail="Episode not found")
        if len(set(request.speaker_ids)) != len(request.speaker_ids):
            raise HTTPException(status_code=422, detail="speaker_ids must not contain duplicates")
        missing = missing_speaker_ids(conn, request.speaker_ids)
        if missing:
            raise HTTPException(status_code=422, detail={"unknown_speaker_ids": missing})
        episode = update_episode(conn, episode_id, request)
    return episode


@router.patch("/{episode_id}/publication", response_model=EpisodeOut)
def update_episode_publication(episode_id: str, request: EpisodePublicationUpdate) -> dict:
    with get_connection() as conn:
        episode = get_episode(conn, episode_id)
        if episode is None:
            raise HTTPException(status_code=404, detail="Episode not found")
        _require_idle_episode(episode)
        set_episode_published(conn, episode_id, request.is_published)
        updated = get_episode(conn, episode_id)
    return updated


@router.delete("/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_episode_detail(episode_id: str) -> None:
    settings = get_settings()
    with get_connection() as conn:
        episode = get_episode(conn, episode_id)
        if episode is None:
            raise HTTPException(status_code=404, detail="Episode not found")
        _require_idle_episode(episode)
        artifact_keys = episode_artifact_keys(conn, episode_id)
        try:
            storage = get_object_storage(settings)
            if episode.get("audio_object_key"):
                storage.delete_object(episode["audio_object_key"])
            if episode.get("artwork_object_key"):
                storage.delete_object(episode["artwork_object_key"])
            for artifact_key in artifact_keys:
                storage.delete_object(artifact_key)
            storage.delete_prefix(f"artifacts/{episode_id}/")
            _remove_episode_directory(settings.upload_root, episode_id)
            _remove_episode_directory(settings.episode_root, episode_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Episode file cleanup failed") from exc
        delete_episode(conn, episode_id)


@router.post("/{episode_id}/transcribe", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
def start_transcription(
    episode_id: str,
    background_tasks: BackgroundTasks,
    request: TranscriptionRequest | None = None,
) -> dict:
    _require_episode(episode_id)
    payload = request or TranscriptionRequest()
    _validate_transcription_request(payload)
    settings = get_settings()
    with get_connection() as conn:
        job = create_job(conn, episode_id, "transcribe", payload.model_dump(exclude_none=True))
    if not settings.external_transcription_worker:
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
        transcript = get_transcript(conn, episode_id)
        if transcript is None:
            raise HTTPException(status_code=409, detail="Episode has no transcript yet")
        _require_complete_speaker_mapping(conn, episode_id, transcript)
        set_episode_published(conn, episode_id, False)
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
    _validate_transcription_request(payload.transcription)
    if payload.transcription.diarize:
        raise HTTPException(
            status_code=409,
            detail="Diarized processing requires transcribe, speaker mapping, then trivia extraction.",
        )
    settings = get_settings()
    with get_connection() as conn:
        set_episode_published(conn, episode_id, False)
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


@router.get("/{episode_id}/speaker-labels", response_model=SpeakerLabelsOut)
def read_speaker_labels(episode_id: str) -> dict:
    episode = _require_episode(episode_id)
    settings = get_settings()
    with get_connection() as conn:
        transcript = get_transcript(conn, episode_id)
        if transcript is None:
            raise HTTPException(status_code=404, detail="Transcript not found")
        mappings = get_speaker_mapping(conn, episode_id)
    labels = _speaker_label_summary(episode_id, episode, transcript, settings)
    return {
        "episode_id": episode_id,
        "speakers": episode["speakers"],
        "mappings": mappings,
        "labels": labels,
    }


@router.get("/{episode_id}/speaker-labels/{label}/sample")
def read_speaker_label_sample(episode_id: str, label: str) -> FileResponse:
    return read_speaker_label_sample_by_index(episode_id, label, 0, legacy_filename=True)


@router.get("/{episode_id}/speaker-labels/{label}/samples/{sample_index}")
def read_speaker_label_sample_by_index(
    episode_id: str,
    label: str,
    sample_index: int,
    legacy_filename: bool = False,
) -> FileResponse:
    episode = _require_episode(episode_id)
    safe_label = sanitize_label(label)
    settings = get_settings()
    with get_connection() as conn:
        transcript = get_transcript(conn, episode_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")
    labels = {item["label"]: item for item in summarize_speaker_labels(transcript)}
    if safe_label not in labels:
        raise HTTPException(status_code=404, detail="Speaker label not found")
    samples = labels[safe_label]["samples"]
    if not samples or sample_index < 0 or sample_index >= len(samples):
        raise HTTPException(status_code=404, detail="Speaker label has no samples")
    sample = samples[sample_index]
    path = ensure_sample_clip(
        ffmpeg_path=settings.ffmpeg_path,
        audio_path=_local_audio_path(episode_id, episode, settings),
        output_dir=settings.episode_root / episode_id / "speaker_samples",
        label=safe_label,
        start=sample["start"],
        end=sample["end"],
        sample_index=None if legacy_filename else sample_index,
    )
    return FileResponse(path, media_type="audio/mpeg", filename=f"{safe_label}.mp3")


@router.get("/{episode_id}/speaker-mapping", response_model=SpeakerMappingOut)
def read_speaker_mapping(episode_id: str) -> dict:
    _require_episode(episode_id)
    with get_connection() as conn:
        return {"episode_id": episode_id, "mappings": get_speaker_mapping(conn, episode_id)}


@router.put("/{episode_id}/speaker-mapping", response_model=SpeakerMappingOut)
def update_speaker_mapping(episode_id: str, request: SpeakerMappingIn) -> dict:
    _require_episode(episode_id)
    with get_connection() as conn:
        transcript = get_transcript(conn, episode_id)
        if transcript is None:
            raise HTTPException(status_code=409, detail="Episode has no transcript yet")
        detected_labels = _detected_speaker_labels(transcript)
        invalid_labels = sorted(set(request.mappings) - detected_labels)
        if invalid_labels:
            raise HTTPException(status_code=422, detail={"unknown_speaker_labels": invalid_labels})
        allowed_speaker_ids = set(speaker_ids_for_episode(conn, episode_id))
        invalid_speaker_ids = sorted(set(request.mappings.values()) - allowed_speaker_ids)
        if invalid_speaker_ids:
            raise HTTPException(
                status_code=422,
                detail={"speaker_ids_not_selected_for_episode": invalid_speaker_ids},
            )
        mappings = replace_speaker_mapping(conn, episode_id, request.mappings)
    return {"episode_id": episode_id, "mappings": mappings}
