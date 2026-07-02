import json
from typing import Any

from ayqm_transcribe.extractor import create_client

from ..config import Settings
from ..schemas import TriviaRephraseOut


class RephraseConfigurationError(RuntimeError):
    pass


class RephraseProviderError(RuntimeError):
    pass


def rephrase_trivia(item: dict[str, Any], settings: Settings) -> TriviaRephraseOut:
    try:
        client = create_client()
    except ValueError as exc:
        raise RephraseConfigurationError(str(exc)) from exc

    prompt = f"""
Rewrite this podcast trivia question and answer for clarity and natural phrasing.
Preserve the factual meaning. Do not add facts, hints, commentary, or formatting.
Return only a JSON object with nullable `question` and `answer` fields.

Trivia item:
{json.dumps({key: item.get(key) for key in ("type", "question", "answer", "keywords")}, ensure_ascii=False)}
""".strip()
    try:
        response = client.models.generate_content(
            model=settings.gemini_model or "gemini-3.1-flash-lite",
            contents=prompt,
            config={
                "temperature": 0.2,
                "max_output_tokens": 1024,
                "response_mime_type": "application/json",
                "response_schema": TriviaRephraseOut,
            },
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, TriviaRephraseOut):
            return parsed
        if isinstance(parsed, dict):
            return TriviaRephraseOut.model_validate(parsed)
        text = getattr(response, "text", None)
        if not text:
            raise ValueError("Gemini response did not include a suggestion")
        return TriviaRephraseOut.model_validate_json(text)
    except Exception as exc:
        raise RephraseProviderError(str(exc)) from exc
