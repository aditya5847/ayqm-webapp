import hashlib
import json
from pathlib import Path
from uuid import uuid4

from .config import Settings
from .db import get_connection
from .repositories import (
    get_episode,
    get_transcript,
    now_utc,
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
            transcript_sha256 = hashlib.sha256(
                json.dumps(transcript, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            model = request.model or settings.gemini_model or "gemini-3.1-flash-lite"
            existing = conn.execute(
                """
                SELECT COUNT(*) FROM gemini_usage
                WHERE episode_id = ? AND model = ? AND prompt_version = 'v1'
                  AND transcript_sha256 = ?
                """,
                [episode_id, model, transcript_sha256],
            ).fetchone()[0]
            if existing:
                update_job_status(conn, job_id, "succeeded")
                return
            spent = float(conn.execute("SELECT COALESCE(SUM(actual_cost_usd), 0) FROM gemini_usage").fetchone()[0])
            if spent >= settings.gemini_historical_budget_usd:
                raise ValueError(
                    f"Gemini application budget of ${settings.gemini_historical_budget_usd:.2f} has been reached"
                )

        trivia, _trivia_path = run_trivia_extraction(
            transcript=transcript,
            episode_dir=settings.episode_root / episode_id,
            request=request,
            settings=settings,
        )

        with get_connection() as conn:
            save_trivia_items(conn, episode_id, trivia)
            if _trivia_path.exists():
                artifact = json.loads(_trivia_path.read_text(encoding="utf-8"))
                usage = artifact.get("usage", {})
                estimated = usage.get("estimated", {})
                actual = usage.get("actual") or {}
                conn.execute(
                    """
                    INSERT INTO gemini_usage VALUES (?, ?, ?, ?, 'v1', ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        str(uuid4()),
                        job_id,
                        episode_id,
                        artifact.get("model") or model,
                        transcript_sha256,
                        int(actual.get("prompt_token_count") or estimated.get("input_tokens") or 0),
                        int(actual.get("candidates_token_count") or 0) + int(actual.get("thoughts_token_count") or 0),
                        float(estimated.get("estimated_input_cost_usd") or 0),
                        float(actual.get("actual_cost_usd") or 0),
                        now_utc(),
                    ],
                )
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
