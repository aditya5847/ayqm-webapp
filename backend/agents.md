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
- Speaker label summaries and max-3-second cached MP3 samples live under
  `/episodes/{episode_id}/speaker-labels`.
- Episode speaker mappings live under
  `/episodes/{episode_id}/speaker-mapping`.

## Important Defaults
- Whisper model: `base`
- Device: `cpu`
- Compute type: `int8`
- Batch size: `16`
- Diarization: enabled by default unless explicitly disabled in the request

## Processing
- Jobs are stored in DuckDB before background work starts.
- Background workers update job status to `running`, `succeeded`, or `failed`.
- Trivia extraction requires a completed diarized transcript and full speaker
  mapping.
- `HF_TOKEN` is required for default diarized transcription unless the request
  explicitly sets `diarize` to `false`.
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` is required in the ayqm-webapp process
  environment for trivia extraction. Put it in the repo-root `.env` for local
  development; do not commit `.env`.
- The local `.env` is loaded by app settings, but `ayqm-transcribe` ultimately
  reads Gemini credentials from `os.environ`, so make sure the server process is
  started with `.env` values loaded.
- When diarization is enabled, selected episode speakers are used only as
  speaker-count hints (`min_speakers`/`max_speakers`). The current
  `ayqm-transcribe` API does not accept known speaker identities.
- Speaker sample clips are generated with `ffmpeg`, capped at 3 seconds, cached
  per episode under `data/episodes/{episode_id}/speaker_samples/`, and reused
  for that episode.
- Trivia `asker` is resolved from `speaker_diarization.asker_speaker` through
  the episode speaker mapping. Without diarization/mapping, `asker` remains
  `null`.
- API consumers should use top-level `asker` as the resolved speaker. The nested
  `speaker_diarization.asker_speaker` value is raw model output such as
  `SPEAKER_00`.
- Ignore extractor-provided trivia IDs for storage. Persist trivia IDs as
  `{episode_id}-trivia-{index}` to avoid collisions across episodes.
- WhisperX 3.8.x exposes diarization at `whisperx.diarize.DiarizationPipeline`;
  keep the webapp compatibility shim unless `ayqm-transcribe` fully handles this
  API shape.

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

## Deferred Public Site and Admin API Task
Implement this work on a separate backend branch. Do not partially expose public
content before publication filtering and public response schemas are in place.

- Add single-admin password authentication. Configure an Argon2 password hash
  with `AYQM_ADMIN_PASSWORD_HASH` and sign sessions with
  `AYQM_SESSION_SECRET`. Expose `POST /auth/login`, `GET /auth/session`, and
  `POST /auth/logout` using a secure HTTP-only, SameSite=Lax cookie. Protect all
  episode, speaker, job, transcript, mapping, and trivia mutation/admin reads.
- Add `episodes.is_published BOOLEAN NOT NULL DEFAULT FALSE`. Existing episodes
  must remain drafts. Publication applies to an entire episode and its remaining
  trivia.
- Add public response schemas that exclude audio/filesystem paths, processing
  state, jobs, raw diarization, and unpublished data. Expose
  `GET /public/episodes`, `GET /public/episodes/{episode_id}`,
  `GET /public/episodes/{episode_id}/trivia`, and paginated
  `GET /public/trivia?limit=&offset=`.
- Add `PATCH /episodes/{episode_id}` for `episode_title`, integer
  `episode_number`, optional description/date/source URL, selected `speaker_ids`,
  and `is_published`. Remove mappings to deselected speakers and require mapping
  to be completed again where necessary.
- Add `PATCH /trivia/{trivia_id}` for type, question, answer, keywords,
  confidence, and an optional real-speaker override; add
  `DELETE /trivia/{trivia_id}`.
- Add `POST /trivia/{trivia_id}/rephrase`. Use the configured Gemini model to
  return a question/answer suggestion without persisting it. The frontend saves
  an accepted suggestion through the normal trivia PATCH endpoint.
- Starting trivia extraction must unpublish the episode because extraction
  replaces its trivia and can discard manual edits. Do not automatically
  republish after completion.
- Add migration, repository, route, authentication, authorization, public-data
  isolation, update/delete, mocked rephrase, and extraction-unpublishing tests.
