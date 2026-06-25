# Backend Context

## Purpose
The backend exposes HTTP APIs for uploading episodes, starting transcription and
trivia extraction, checking job status, and reading stored transcript/trivia
results.

## Important Defaults
- Whisper model: `base`
- Device: `cpu`
- Compute type: `int8`
- Batch size: `16`
- Diarization: disabled unless requested

## Processing
- Jobs are stored in DuckDB before background work starts.
- Background workers update job status to `running`, `succeeded`, or `failed`.
- Trivia extraction requires a completed transcript.
- `HF_TOKEN` is only required for diarization.
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` is required for trivia extraction.

## Testing
Tests should monkeypatch `ayqm-transcribe` integration points instead of invoking
WhisperX or Gemini.

