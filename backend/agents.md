# Backend Context

## Purpose
The backend exposes HTTP APIs for uploading episodes, starting transcription and
trivia extraction, checking job status, and reading stored transcript/trivia
results. It also manages the global speaker list and maps diarization labels to
known episode speakers.

## API Contract
- `POST /episodes` accepts multipart form data, not a JSON body.
- Upload fields are `file`, `episode_title`, integer `episode_number`, optional
  `episode_description`, optional `published_at`, optional `source_url`,
  required JSON-string `speaker_ids`, and optional JSON-string `extra_metadata`.
- `speaker_ids` must be a JSON array of speaker ID strings, for example
  `["8ac5d1d1-06aa-44bf-baf3-32720c215b5f"]`, not speaker objects.
- Episode responses use `episode_title`; do not add back `title`, `show_title`,
  or `show_name`.
- Speaker CRUD lives under `/speakers`.
- Episode speaker mappings live under
  `/episodes/{episode_id}/speaker-mapping`.

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
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` is required in the ayqm-webapp process
  environment for trivia extraction. Put it in the repo-root `.env` for local
  development; do not commit `.env`.
- The local `.env` is loaded by app settings, but `ayqm-transcribe` ultimately
  reads Gemini credentials from `os.environ`, so make sure the server process is
  started with `.env` values loaded.
- When diarization is enabled, selected episode speakers are used only as
  speaker-count hints (`min_speakers`/`max_speakers`). The current
  `ayqm-transcribe` API does not accept known speaker identities.
- Trivia `asker` is resolved from `speaker_diarization.asker_speaker` through
  the episode speaker mapping. Without diarization/mapping, `asker` remains
  `null`.

## Storage
- DuckDB path defaults to `data/ayqm.duckdb`.
- Uploaded audio is under `data/uploads/{episode_id}/`.
- Transcript and trivia artifacts are under `data/episodes/{episode_id}/`.
- Do not commit `data/`, audio files, generated transcript/trivia JSON, or
  DuckDB files.

## Testing
Tests should monkeypatch `ayqm-transcribe` integration points instead of invoking
WhisperX or Gemini.
- Use `/Users/adityasrivastava/.local/bin/uv run pytest`.
