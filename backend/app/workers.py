from pathlib import Path

from .config import Settings
from .db import get_connection
from .repositories import (
    get_episode,
    get_transcript,
    save_transcript,
    save_trivia_items,
    speaker_ids_for_episode,
    update_job_status,
)
from .schemas import ProcessRequest, TranscriptionRequest, TriviaExtractionRequest
from .services.transcription import run_transcription
from .services.trivia import run_trivia_extraction


def _with_episode_speaker_count(
    conn,
    episode_id: str,
    request: TranscriptionRequest,
) -> TranscriptionRequest:
    if not request.diarize:
        return request
    speaker_count = len(speaker_ids_for_episode(conn, episode_id))
    if speaker_count == 0:
        return request
    return request.model_copy(
        update={
            "min_speakers": request.min_speakers or speaker_count,
            "max_speakers": request.max_speakers or speaker_count,
        }
    )


def transcribe_episode_job(
    job_id: str,
    episode_id: str,
    request: TranscriptionRequest,
    settings: Settings,
) -> None:
    try:
        with get_connection() as conn:
            update_job_status(conn, job_id, "running")
            episode = get_episode(conn, episode_id)
            if episode is None:
                raise ValueError(f"Episode not found: {episode_id}")
            request = _with_episode_speaker_count(conn, episode_id, request)

        episode_dir = settings.episode_root / episode_id
        transcript, transcript_path = run_transcription(
            audio_path=episode["audio_path"],
            episode_dir=episode_dir,
            request=request,
            settings=settings,
        )

        with get_connection() as conn:
            save_transcript(conn, episode_id, str(transcript_path), transcript)
            update_job_status(conn, job_id, "succeeded")
    except Exception as exc:
        with get_connection() as conn:
            update_job_status(conn, job_id, "failed", str(exc))


def extract_trivia_job(
    job_id: str,
    episode_id: str,
    request: TriviaExtractionRequest,
    settings: Settings,
) -> None:
    try:
        with get_connection() as conn:
            update_job_status(conn, job_id, "running")
            transcript = get_transcript(conn, episode_id)
            if transcript is None:
                raise ValueError(f"Transcript not found for episode: {episode_id}")

        trivia, _trivia_path = run_trivia_extraction(
            transcript=transcript,
            episode_dir=settings.episode_root / episode_id,
            request=request,
            settings=settings,
        )

        with get_connection() as conn:
            save_trivia_items(conn, episode_id, trivia)
            update_job_status(conn, job_id, "succeeded")
    except Exception as exc:
        with get_connection() as conn:
            update_job_status(conn, job_id, "failed", str(exc))


def process_episode_job(
    job_id: str,
    episode_id: str,
    request: ProcessRequest,
    settings: Settings,
) -> None:
    try:
        with get_connection() as conn:
            update_job_status(conn, job_id, "running")
            episode = get_episode(conn, episode_id)
            if episode is None:
                raise ValueError(f"Episode not found: {episode_id}")
            transcription_request = _with_episode_speaker_count(conn, episode_id, request.transcription)

        episode_dir = Path(settings.episode_root) / episode_id
        transcript, transcript_path = run_transcription(
            audio_path=episode["audio_path"],
            episode_dir=episode_dir,
            request=transcription_request,
            settings=settings,
        )
        trivia, _trivia_path = run_trivia_extraction(
            transcript=transcript,
            episode_dir=episode_dir,
            request=request.trivia,
            settings=settings,
        )

        with get_connection() as conn:
            save_transcript(conn, episode_id, str(transcript_path), transcript)
            save_trivia_items(conn, episode_id, trivia)
            update_job_status(conn, job_id, "succeeded")
    except Exception as exc:
        with get_connection() as conn:
            update_job_status(conn, job_id, "failed", str(exc))
