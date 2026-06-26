import re
import subprocess
from pathlib import Path
from typing import Any


MAX_SAMPLE_SECONDS = 3.0
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def sanitize_label(label: str) -> str:
    if not LABEL_PATTERN.match(label):
        raise ValueError(f"Invalid speaker label: {label}")
    return label


def speaker_labels_from_transcript(transcript: dict[str, Any]) -> list[str]:
    return [item["label"] for item in summarize_speaker_labels(transcript)]


def summarize_speaker_labels(transcript: dict[str, Any], max_samples: int = 3) -> list[dict[str, Any]]:
    labels: dict[str, dict[str, Any]] = {}
    for segment in transcript.get("segments", []):
        if not isinstance(segment, dict):
            continue
        label = segment.get("speaker")
        if label:
            _add_label_sample(labels, str(label), segment, max_samples)
            continue
        for word in segment.get("words") or []:
            if isinstance(word, dict) and word.get("speaker"):
                word_segment = {
                    "start": word.get("start", segment.get("start", 0)),
                    "end": word.get("end", segment.get("end", segment.get("start", 0))),
                    "text": segment.get("text") or word.get("word") or "",
                }
                _add_label_sample(labels, str(word["speaker"]), word_segment, max_samples)

    return [
        {
            "label": label,
            "segment_count": data["segment_count"],
            "first_seen": data["first_seen"],
            "last_seen": data["last_seen"],
            "samples": data["samples"],
        }
        for label, data in sorted(labels.items())
    ]


def _add_label_sample(
    labels: dict[str, dict[str, Any]],
    label: str,
    segment: dict[str, Any],
    max_samples: int,
) -> None:
    start = float(segment.get("start") or 0)
    end = float(segment.get("end") or start)
    entry = labels.setdefault(
        label,
        {
            "segment_count": 0,
            "first_seen": start,
            "last_seen": end,
            "samples": [],
        },
    )
    entry["segment_count"] += 1
    entry["first_seen"] = min(entry["first_seen"], start)
    entry["last_seen"] = max(entry["last_seen"], end)
    if len(entry["samples"]) < max_samples:
        entry["samples"].append(
            {
                "start": start,
                "end": end,
                "text": str(segment.get("text") or "").strip(),
            }
        )


def ensure_sample_clip(
    *,
    ffmpeg_path: str,
    audio_path: str,
    output_dir: Path,
    label: str,
    start: float,
    end: float,
    sample_index: int | None = None,
) -> Path:
    safe_label = sanitize_label(label)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"-{sample_index}" if sample_index is not None else ""
    output_path = output_dir / f"{safe_label}{suffix}.mp3"
    if output_path.exists():
        return output_path

    duration = max(0.1, min(MAX_SAMPLE_SECONDS, float(end) - float(start)))
    subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-ss",
            f"{max(0.0, float(start)):.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            audio_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
    return output_path
