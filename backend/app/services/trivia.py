import json
from pathlib import Path

from ayqm_transcribe.extractor import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    create_client,
    extract_trivia,
)

from ..config import Settings
from ..schemas import TriviaExtractionRequest


def run_trivia_extraction(
    transcript: dict,
    episode_dir: Path,
    request: TriviaExtractionRequest,
    settings: Settings,
) -> tuple[list, Path]:
    episode_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = episode_dir / "transcript.json"
    if not transcript_path.exists():
        with transcript_path.open("w", encoding="utf-8") as output:
            json.dump(transcript, output, indent=2, ensure_ascii=False)

    client = create_client()
    extraction = extract_trivia(
        transcript_path,
        client=client,
        model=request.model or settings.gemini_model or "gemini-3.1-flash-lite",
        max_output_tokens=request.max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS,
    )

    trivia_path = episode_dir / "trivia.json"
    with trivia_path.open("w", encoding="utf-8") as output:
        json.dump(extraction.model_dump(), output, indent=2, ensure_ascii=False)

    return extraction.trivia, trivia_path

