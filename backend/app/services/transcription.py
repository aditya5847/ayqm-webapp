import json
import os
from pathlib import Path

from ayqm_transcribe.transcriber import WhisperXEncoder, transcribe_audio

from ..config import Settings
from ..schemas import TranscriptionRequest


def run_transcription(
    audio_path: str,
    episode_dir: Path,
    request: TranscriptionRequest,
    settings: Settings,
) -> tuple[dict, Path]:
    hf_token = request.hf_token or os.environ.get("HF_TOKEN")
    transcript = transcribe_audio(
        audio_path=audio_path,
        model_name=request.model_name or settings.whisper_model,
        device=request.device or settings.whisper_device,
        compute_type=request.compute_type or settings.whisper_compute_type,
        batch_size=request.batch_size or settings.whisper_batch_size,
        diarize=request.diarize,
        hf_token=hf_token,
        min_speakers=request.min_speakers,
        max_speakers=request.max_speakers,
    )

    episode_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = episode_dir / "transcript.json"
    with transcript_path.open("w", encoding="utf-8") as output:
        json.dump(transcript, output, cls=WhisperXEncoder, indent=2, ensure_ascii=False)

    return transcript, transcript_path

