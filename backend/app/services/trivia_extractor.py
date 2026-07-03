import os
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field


DEFAULT_MAX_OUTPUT_TOKENS = 8192
DEFAULT_INPUT_PRICE_PER_1M = 0.25
DEFAULT_OUTPUT_PRICE_PER_1M = 1.50


class TimestampRange(BaseModel):
    start: float
    end: float
    display: str


class SpeakerDiarization(BaseModel):
    asker_speaker: str | None = None
    answerer_speakers: list[str] = Field(default_factory=list)
    mentioned_by_speakers: list[str] = Field(default_factory=list)


class TriviaItem(BaseModel):
    id: str
    type: str
    question: str | None = None
    answer: str | None = None
    keywords: list[str] = Field(default_factory=list)
    timestamps: TimestampRange
    speaker_diarization: SpeakerDiarization = Field(default_factory=SpeakerDiarization)
    confidence: str = "medium"


class TriviaExtraction(BaseModel):
    trivia: list[TriviaItem] = Field(default_factory=list)


class EstimatedUsage(BaseModel):
    input_tokens: int
    estimated_input_cost_usd: float


class ActualUsage(BaseModel):
    prompt_token_count: int = 0
    candidates_token_count: int = 0
    thoughts_token_count: int = 0
    total_token_count: int = 0
    actual_cost_usd: float = 0.0


class UsageReport(BaseModel):
    estimated: EstimatedUsage
    actual: ActualUsage | None = None


class ExtractionOutput(BaseModel):
    source_transcript: str
    model: str
    usage: UsageReport
    trivia: list[TriviaItem]


def create_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY or GOOGLE_API_KEY in the process environment.")
    return genai.Client(api_key=api_key)


def format_timestamp(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def normalize_segments(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = []
    for segment in transcript.get("segments", []):
        if not isinstance(segment, dict) or not str(segment.get("text") or "").strip():
            continue
        start = float(segment.get("start") or 0)
        end = float(segment.get("end") or start)
        normalized.append(
            {
                "start": start,
                "end": end,
                "display": f"{format_timestamp(start)}-{format_timestamp(end)}",
                "speaker": segment.get("speaker") or "UNKNOWN",
                "text": str(segment["text"]).strip(),
            }
        )
    return normalized


def build_prompt(transcript: dict[str, Any]) -> str:
    lines = [
        f'[{segment["display"]}] speaker={segment["speaker"]}: {segment["text"]}'
        for segment in normalize_segments(transcript)
    ]
    return """Extract trivia from this podcast transcript.

Return high-recall trivia items of two types:
- asked_question: a quiz/trivia question actually asked in the episode.
- mentioned_trivia: a self-contained factual claim mentioned in conversation that could plausibly become a quiz question.

Do not extract hints, transcript excerpts, or segment ids. Preserve asked questions when possible and include their answers when present. For mentioned trivia, write a concise quiz-style question and put the fact in the answer. Use transcript-relative timestamps. Speaker fields must use only labels present in the transcript. Keep keywords short and useful for search.

Transcript:
""" + "\n".join(lines)


def _actual_usage(response: Any) -> ActualUsage:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return ActualUsage()
    prompt = int(getattr(usage, "prompt_token_count", 0) or 0)
    candidates = int(getattr(usage, "candidates_token_count", 0) or 0)
    thoughts = int(getattr(usage, "thoughts_token_count", 0) or 0)
    input_price = float(os.environ.get("AYQM_GEMINI_INPUT_PRICE_PER_1M", DEFAULT_INPUT_PRICE_PER_1M))
    output_price = float(os.environ.get("AYQM_GEMINI_OUTPUT_PRICE_PER_1M", DEFAULT_OUTPUT_PRICE_PER_1M))
    cost = prompt / 1_000_000 * input_price
    cost += (candidates + thoughts) / 1_000_000 * output_price
    return ActualUsage(
        prompt_token_count=prompt,
        candidates_token_count=candidates,
        thoughts_token_count=thoughts,
        total_token_count=int(getattr(usage, "total_token_count", 0) or 0),
        actual_cost_usd=round(cost, 6),
    )


def extract_trivia(
    transcript_path: Path,
    *,
    client: genai.Client,
    model: str,
    max_output_tokens: int,
) -> ExtractionOutput:
    import json

    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    prompt = build_prompt(transcript)
    count = client.models.count_tokens(model=model, contents=prompt)
    input_tokens = int(getattr(count, "total_tokens", 0) or 0)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            response_schema=TriviaExtraction,
        ),
    )
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, TriviaExtraction):
        extraction = parsed
    elif parsed is not None:
        extraction = TriviaExtraction.model_validate(parsed)
    else:
        extraction = TriviaExtraction.model_validate_json(response.text)
    input_price = float(os.environ.get("AYQM_GEMINI_INPUT_PRICE_PER_1M", DEFAULT_INPUT_PRICE_PER_1M))
    return ExtractionOutput(
        source_transcript=str(transcript_path),
        model=model,
        usage=UsageReport(
            estimated=EstimatedUsage(
                input_tokens=input_tokens,
                estimated_input_cost_usd=round(input_tokens / 1_000_000 * input_price, 6),
            ),
            actual=_actual_usage(response),
        ),
        trivia=extraction.trivia,
    )
