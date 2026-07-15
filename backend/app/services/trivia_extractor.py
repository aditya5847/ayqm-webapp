import os
from pathlib import Path
import re
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field


PROMPT_VERSION = "v2"
DEFAULT_MAX_OUTPUT_TOKENS = 8192
DEFAULT_CHUNK_TARGET_CHARS = 18000
DEFAULT_CHUNK_OVERLAP_SEGMENTS = 2
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
    id: str | None = None
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


def _segment_line(segment: dict[str, Any]) -> str:
    return f'[{segment["display"]}] speaker={segment["speaker"]}: {segment["text"]}'


def chunk_segments(
    segments: list[dict[str, Any]],
    *,
    target_chars: int = DEFAULT_CHUNK_TARGET_CHARS,
    overlap_segments: int = DEFAULT_CHUNK_OVERLAP_SEGMENTS,
) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for segment in segments:
        line_length = len(_segment_line(segment)) + 1
        if current and current_chars + line_length > target_chars:
            chunks.append(current)
            current = current[-overlap_segments:] if overlap_segments > 0 else []
            current_chars = sum(len(_segment_line(item)) + 1 for item in current)
        current.append(segment)
        current_chars += line_length
    if current:
        chunks.append(current)
    return chunks


def build_prompt(transcript: dict[str, Any] | list[dict[str, Any]]) -> str:
    segments = normalize_segments(transcript) if isinstance(transcript, dict) else transcript
    lines = [
        _segment_line(segment)
        for segment in segments
    ]
    return """You are a strict transcript-grounded trivia extractor and quiz editor.

Extract high-quality trivia from this podcast transcript chunk from beginning to end. Do not stop early. Aim for high recall while preserving strict transcript grounding and quiz quality.

Return a JSON object matching the provided schema, with a top-level "trivia" array. Each item must be exactly one of:
- asked_question: a quiz/trivia question actually asked in the episode.
- mentioned_trivia: a factual claim from the conversation that can be rewritten as a self-contained quiz question.

Only include facts, questions, answers, and connections that are directly supported by this transcript chunk. Do not add outside knowledge, infer unstated common links, invent missing answers, or add aliases/tags that are not supported by the transcript.

For each item, include:
- type
- question
- answer
- transcript-relative timestamp range
- confidence
- speaker diarization labels exactly as they appear in the transcript
- keywords

Question quality guidelines:
- Avoid repetitive phrasing.
- Combine sequential facts about the same topic into one stronger multi-layered question when they clearly belong together.
- Prefer interesting, surprising, or quiz-worthy facts over trivial mentions.
- Preserve asked questions when possible instead of over-rewriting them.
- Do not extract hints, banter, vague claims, incomplete facts, or facts without enough transcript support.

When rewriting mentioned trivia, choose the best quiz style only if supported by the transcript:
- Concealed Star: use when an obscure backstory points to a famous answer. Use generic terms or variables such as "X" to mask the famous entity in the question, and reveal the famous entity only in the answer.
- Common Link: use only when the transcript explicitly connects multiple entities. The connection must be stated or clearly established in the transcript.
- Surprising Mechanism: use when the interesting part is the mechanism, reason, law, strategy, quirk, or coincidence.

Keyword guidelines:
Include 4-8 concise search keywords or short phrases for each item. These keywords are used for full-text search, so they should improve discoverability without adding unsupported meaning.

Prefer:
- the answer entity name
- important names, places, works, events, organizations, or concepts mentioned in the item
- topic/category terms that are directly supported by the transcript
- natural search phrases a visitor might use
- alternate spellings or aliases only if they appear in or are directly supported by the transcript

Avoid:
- generic filler terms such as "trivia", "podcast", "fact", "question", "answer", "episode", or "quiz"
- overly broad tags that could apply to many unrelated items
- speculative labels
- outside-knowledge aliases not present in the transcript
- speaker names unless the speaker identity is itself part of the trivia

Speaker diarization rules:
- Use only speaker labels exactly as they appear in the transcript, such as "SPEAKER_00".
- Do not invent real speaker names.
- For asked_question, set asker_speaker when the transcript supports who asked it.
- For mentioned_trivia, use mentioned_by_speakers when the transcript supports who mentioned the fact.
- Leave uncertain speaker fields empty rather than guessing.

Timestamp rules:
- Use transcript-relative timestamps.
- The timestamp range should cover the source discussion that supports the trivia item.
- If a combined item uses multiple adjacent facts, use a range that covers the combined discussion.

Quality bar:
A valid trivia item should be understandable without reading the transcript. The question should be clear, the answer should be specific, and the item should have enough support in the transcript chunk to avoid hallucination.

Transcript chunk:
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


def _merge_actual_usage(usages: list[ActualUsage]) -> ActualUsage:
    return ActualUsage(
        prompt_token_count=sum(usage.prompt_token_count for usage in usages),
        candidates_token_count=sum(usage.candidates_token_count for usage in usages),
        thoughts_token_count=sum(usage.thoughts_token_count for usage in usages),
        total_token_count=sum(usage.total_token_count for usage in usages),
        actual_cost_usd=round(sum(usage.actual_cost_usd for usage in usages), 6),
    )


def _dedupe_key(item: TriviaItem) -> tuple[str, str, str]:
    question = re.sub(r"\s+", " ", item.question or "").strip().lower()
    answer = re.sub(r"\s+", " ", item.answer or "").strip().lower()
    return (item.type.strip().lower(), question, answer)


def _dedupe_trivia(items: list[TriviaItem]) -> list[TriviaItem]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[TriviaItem] = []
    for item in items:
        key = _dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _parse_extraction(response: Any) -> TriviaExtraction:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, TriviaExtraction):
        return parsed
    if parsed is not None:
        return TriviaExtraction.model_validate(parsed)
    return TriviaExtraction.model_validate_json(response.text)


def extract_trivia(
    transcript_path: Path,
    *,
    client: genai.Client,
    model: str,
    max_output_tokens: int,
) -> ExtractionOutput:
    import json

    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    chunks = chunk_segments(normalize_segments(transcript))
    input_tokens = 0
    actual_usages: list[ActualUsage] = []
    trivia: list[TriviaItem] = []
    for chunk in chunks:
        prompt = build_prompt(chunk)
        count = client.models.count_tokens(model=model, contents=prompt)
        input_tokens += int(getattr(count, "total_tokens", 0) or 0)
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
        trivia.extend(_parse_extraction(response).trivia)
        actual_usages.append(_actual_usage(response))
    input_price = float(os.environ.get("AYQM_GEMINI_INPUT_PRICE_PER_1M", DEFAULT_INPUT_PRICE_PER_1M))
    return ExtractionOutput(
        source_transcript=str(transcript_path),
        model=model,
        usage=UsageReport(
            estimated=EstimatedUsage(
                input_tokens=input_tokens,
                estimated_input_cost_usd=round(input_tokens / 1_000_000 * input_price, 6),
            ),
            actual=_merge_actual_usage(actual_usages),
        ),
        trivia=_dedupe_trivia(trivia),
    )
