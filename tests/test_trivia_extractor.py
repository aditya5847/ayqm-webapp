import json
from types import SimpleNamespace

from backend.app.services import trivia_extractor
from backend.app.services.trivia_extractor import (
    SpeakerDiarization,
    TimestampRange,
    TriviaExtraction,
    TriviaItem,
    build_prompt,
    extract_trivia,
    normalize_trivia_timestamps,
)


def _item(start, end, display="stale"):
    return TriviaItem(
        type="mentioned_trivia",
        question="What happened?",
        answer="Something happened.",
        keywords=["something"],
        timestamps=TimestampRange(start=start, end=end, display=display),
        speaker_diarization=SpeakerDiarization(mentioned_by_speakers=["SPEAKER_00"]),
        confidence="high",
    )


def test_prompt_makes_chunk_timestamps_absolute():
    prompt = build_prompt(
        [
            {
                "start": 3600.0,
                "end": 3610.0,
                "display": "01:00:00-01:00:10",
                "speaker": "SPEAKER_00",
                "text": "A fact from later in the episode.",
            }
        ]
    )

    assert "This chunk covers 01:00:00-01:00:10 on the full episode timeline" in prompt
    assert "Return timestamps on that same full-episode timeline" in prompt
    assert "Do not reset timestamps to 00:00:00 for the start of this chunk" in prompt


def test_normalize_trivia_timestamps_offsets_likely_chunk_relative_values():
    chunk = [
        {
            "start": 3600.0,
            "end": 3620.0,
            "display": "01:00:00-01:00:20",
            "speaker": "SPEAKER_00",
            "text": "A fact from later in the episode.",
        }
    ]

    normalized = normalize_trivia_timestamps([_item(5.0, 8.0)], chunk)

    assert len(normalized) == 1
    assert normalized[0].timestamps.start == 3605.0
    assert normalized[0].timestamps.end == 3608.0
    assert normalized[0].timestamps.display == "01:00:05-01:00:08"


def test_normalize_trivia_timestamps_preserves_absolute_values_and_regenerates_display():
    chunk = [
        {
            "start": 3600.0,
            "end": 3620.0,
            "display": "01:00:00-01:00:20",
            "speaker": "SPEAKER_00",
            "text": "A fact from later in the episode.",
        }
    ]

    normalized = normalize_trivia_timestamps([_item(3605.0, 3608.0, "00:00:05-00:00:08")], chunk)

    assert len(normalized) == 1
    assert normalized[0].timestamps.start == 3605.0
    assert normalized[0].timestamps.end == 3608.0
    assert normalized[0].timestamps.display == "01:00:05-01:00:08"


def test_normalize_trivia_timestamps_drops_unmappable_values():
    chunk = [
        {
            "start": 3600.0,
            "end": 3620.0,
            "display": "01:00:00-01:00:20",
            "speaker": "SPEAKER_00",
            "text": "A fact from later in the episode.",
        }
    ]

    assert normalize_trivia_timestamps([_item(7200.0, 7210.0)], chunk) == []


def test_extract_trivia_corrects_chunk_relative_timestamps(tmp_path, monkeypatch):
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(
        json.dumps(
            {
                "segments": [
                    {"start": 0, "end": 10, "speaker": "SPEAKER_00", "text": "First chunk fact."},
                    {"start": 3600, "end": 3620, "speaker": "SPEAKER_00", "text": "Later chunk fact."},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        trivia_extractor,
        "chunk_segments",
        lambda segments: [[segments[0]], [segments[1]]],
    )

    responses = [
        TriviaExtraction(trivia=[]),
        TriviaExtraction(trivia=[_item(5.0, 8.0, "00:00:05-00:00:08")]),
    ]

    class Models:
        def count_tokens(self, **kwargs):
            return SimpleNamespace(total_tokens=10)

        def generate_content(self, **kwargs):
            return SimpleNamespace(parsed=responses.pop(0), usage_metadata=None)

    output = extract_trivia(
        transcript_path,
        client=SimpleNamespace(models=Models()),
        model="gemini-test",
        max_output_tokens=8192,
    )

    assert len(output.trivia) == 1
    assert output.trivia[0].timestamps.start == 3605.0
    assert output.trivia[0].timestamps.end == 3608.0
    assert output.trivia[0].timestamps.display == "01:00:05-01:00:08"
