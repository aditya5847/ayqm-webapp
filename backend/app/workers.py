import hashlib
import json
from pathlib import Path
from uuid import uuid4

from .config import Settings
from .db import get_connection
from .repositories import (
    get_episode,
    get_trivia_candidate,
    get_transcript,
    mark_trivia_candidate_failed,
    mark_trivia_candidate_ready,
    now_utc,
    record_episode_trivia_extraction,
    save_transcript,
    save_trivia_items,
    speaker_ids_for_episode,
    update_job_status,
)
from .schemas import ProcessRequest, TranscriptionRequest, TriviaExtractionRequest
from .services.trivia import run_trivia_extraction
from .services.trivia_extractor import PROMPT_VERSION, TRIVIA_EXTRACTION_RELEASE


def run_transcription(*args, **kwargs):
    from .services.transcription import run_transcription as implementation

    return implementation(*args, **kwargs)


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


def _transcript_sha256(transcript: dict) -> str:
    return hashlib.sha256(
        json.dumps(transcript, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _record_gemini_usage(
    conn,
    *,
    job_id: str,
    episode_id: str,
    model: str,
    transcript_sha256: str,
    artifact: dict,
) -> None:
    usage = artifact.get("usage", {})
    estimated = usage.get("estimated", {})
    actual = usage.get("actual") or {}
    conn.execute(
        """
        INSERT INTO gemini_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            str(uuid4()),
            job_id,
            episode_id,
            artifact.get("model") or model,
            PROMPT_VERSION,
            transcript_sha256,
            int(actual.get("prompt_token_count") or estimated.get("input_tokens") or 0),
            int(actual.get("candidates_token_count") or 0) + int(actual.get("thoughts_token_count") or 0),
            float(estimated.get("estimated_input_cost_usd") or 0),
            float(actual.get("actual_cost_usd") or 0),
            now_utc(),
        ],
    )


def _check_gemini_budget(conn, settings: Settings) -> None:
    spent = float(conn.execute("SELECT COALESCE(SUM(actual_cost_usd), 0) FROM gemini_usage").fetchone()[0])
    if spent >= settings.gemini_historical_budget_usd:
        raise ValueError(f"Gemini application budget of ${settings.gemini_historical_budget_usd:.2f} has been reached")


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
            transcript_sha256 = _transcript_sha256(transcript)
            model = request.model or settings.gemini_model or "gemini-3.1-flash-lite"
            existing = conn.execute(
                """
                SELECT COUNT(*) FROM gemini_usage
                WHERE episode_id = ? AND model = ? AND prompt_version = ?
                  AND transcript_sha256 = ?
                """,
                [episode_id, model, PROMPT_VERSION, transcript_sha256],
            ).fetchone()[0]
            if existing:
                record_episode_trivia_extraction(
                    conn,
                    episode_id=episode_id,
                    release_version=TRIVIA_EXTRACTION_RELEASE,
                    prompt_version=PROMPT_VERSION,
                    model=model,
                    transcript_sha256=transcript_sha256,
                    job_id=job_id,
                )
                update_job_status(conn, job_id, "succeeded")
                return
            _check_gemini_budget(conn, settings)

        trivia, _trivia_path = run_trivia_extraction(
            transcript=transcript,
            episode_dir=settings.episode_root / episode_id,
            request=request,
            settings=settings,
        )

        with get_connection() as conn:
            save_trivia_items(conn, episode_id, trivia)
            artifact = {}
            if _trivia_path.exists():
                artifact = json.loads(_trivia_path.read_text(encoding="utf-8"))
                _record_gemini_usage(
                    conn,
                    job_id=job_id,
                    episode_id=episode_id,
                    model=model,
                    transcript_sha256=transcript_sha256,
                    artifact=artifact,
                )
            record_episode_trivia_extraction(
                conn,
                episode_id=episode_id,
                release_version=TRIVIA_EXTRACTION_RELEASE,
                prompt_version=PROMPT_VERSION,
                model=artifact.get("model") or model,
                transcript_sha256=transcript_sha256,
                job_id=job_id,
            )
            update_job_status(conn, job_id, "succeeded")
    except Exception as exc:
        with get_connection() as conn:
            update_job_status(conn, job_id, "failed", str(exc))


def extract_trivia_candidate_job(
    job_id: str,
    candidate_id: str,
    request: TriviaExtractionRequest,
    settings: Settings,
) -> None:
    try:
        with get_connection() as conn:
            update_job_status(conn, job_id, "running")
            candidate = get_trivia_candidate(conn, candidate_id)
            if candidate is None:
                raise ValueError(f"Trivia candidate not found: {candidate_id}")
            transcript = get_transcript(conn, candidate["episode_id"])
            if transcript is None:
                raise ValueError(f"Transcript not found for episode: {candidate['episode_id']}")
            transcript_sha256 = _transcript_sha256(transcript)
            if transcript_sha256 != candidate["transcript_sha256"]:
                raise ValueError("Transcript changed before trivia candidate generation")
            _check_gemini_budget(conn, settings)

        _trivia, trivia_path = run_trivia_extraction(
            transcript=transcript,
            episode_dir=settings.episode_root / candidate["episode_id"] / "candidates" / candidate_id,
            request=request,
            settings=settings,
        )

        with get_connection() as conn:
            artifact = json.loads(trivia_path.read_text(encoding="utf-8"))
            mark_trivia_candidate_ready(
                conn,
                candidate_id,
                candidate_json={"trivia": artifact.get("trivia", [])},
                usage_json=artifact.get("usage", {}),
            )
            _record_gemini_usage(
                conn,
                job_id=job_id,
                episode_id=candidate["episode_id"],
                model=artifact.get("model") or candidate["model"],
                transcript_sha256=candidate["transcript_sha256"],
                artifact=artifact,
            )
            update_job_status(conn, job_id, "succeeded")
    except Exception as exc:
        with get_connection() as conn:
            mark_trivia_candidate_failed(conn, candidate_id, str(exc))
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
            transcript_sha256 = _transcript_sha256(transcript)
            model = request.trivia.model or settings.gemini_model or "gemini-3.1-flash-lite"
            artifact = {}
            if _trivia_path.exists():
                artifact = json.loads(_trivia_path.read_text(encoding="utf-8"))
                _record_gemini_usage(
                    conn,
                    job_id=job_id,
                    episode_id=episode_id,
                    model=model,
                    transcript_sha256=transcript_sha256,
                    artifact=artifact,
                )
            record_episode_trivia_extraction(
                conn,
                episode_id=episode_id,
                release_version=TRIVIA_EXTRACTION_RELEASE,
                prompt_version=PROMPT_VERSION,
                model=artifact.get("model") or model,
                transcript_sha256=transcript_sha256,
                job_id=job_id,
            )
            update_job_status(conn, job_id, "succeeded")
    except Exception as exc:
        with get_connection() as conn:
            update_job_status(conn, job_id, "failed", str(exc))
