# Project: ayqm-webapp

## Overview
`ayqm-webapp` is a FastAPI backend for podcast audio ingestion, transcription,
trivia extraction, and DuckDB-backed storage. A future frontend will live in the
root-level `frontend/` folder.

## Tech Stack
- Python 3.12+
- FastAPI
- DuckDB
- uv
- Local editable dependency: `../ayqm-transcribe`

## Operational Rules
- Use `/Users/adityasrivastava/.local/bin/uv` for uv commands.
- Keep `ayqm-transcribe` as an editable path dependency during local
  development.
- Do not commit audio files, generated transcripts, trivia artifacts, or DuckDB
  database files.
- Do not commit `.env`; it is ignored and may contain `GOOGLE_API_KEY` or
  `GEMINI_API_KEY` for trivia extraction.
- Default transcription settings should stay macOS-safe: CPU and `int8`.

## Architecture
- Backend code lives in `backend/app`.
- Uploaded audio is stored under `data/uploads/{episode_id}/`.
- Generated transcript/trivia artifacts are stored under
  `data/episodes/{episode_id}/`.
- DuckDB stores episode metadata, speakers, episode-speaker selections, jobs,
  transcripts, and trivia rows.
- Background processing uses FastAPI in-process background tasks for v1.
- Production uses one FastAPI/Uvicorn process and one Railway replica. DuckDB
  must never be opened by the Runpod or Mac transcription worker.
- Production audio and artifacts use private Cloudflare R2 object keys. Local
  development retains filesystem storage.
- External transcription workers claim leased jobs through `/worker/jobs/*`,
  use presigned R2 URLs, and submit artifact references back to the API. The
  transcript upload URL is issued only after transcription so it cannot expire
  during a long-running job.
- RSS imports are keyed by GUID and support main, mini, and unnumbered
  announcement items. The clean production database must not be seeded from the
  local DuckDB file.
- Episode metadata uses `episode_title`, integer `episode_number`,
  optional `episode_description`, optional `published_at`, optional
  `source_url`, `extra_metadata`, and selected `speaker_ids`. Do not reintroduce
  `title`, `show_title`, or `show_name`.
- Speakers are global records with `id` and `name`. Episode speakers are
  selected at upload time. Diarization label mappings can later map labels such
  as `SPEAKER_00` to selected episode speakers so trivia items can expose
  `asker`.
- Transcription diarizes by default. Speaker labels must be mapped before trivia
  extraction. Mapping UI should use `GET /episodes/{episode_id}/speaker-labels`
  and the per-label sample clip endpoints.
- Trivia API consumers should use the top-level `asker` object for real speaker
  identity. `speaker_diarization.asker_speaker` is the raw diarization label.
- Stored trivia row IDs are generated as `{episode_id}-trivia-{index}` because
  extractor-provided IDs can repeat across episodes.

## Current API Notes
- Admin APIs require the signed cookie obtained from `POST /auth/login`.
- Public published-content reads are exposed under `/public`; their schemas omit
  paths, processing state, raw diarization, and draft content.
- Episode-level `is_published` defaults to false. Starting trivia extraction or
  processing returns the episode to draft.
- `POST /episodes` is multipart form data with fields: `file`,
  `episode_title`, integer `episode_number`, optional `episode_description`,
  optional `published_at`, optional `source_url`, required JSON-string
  `speaker_ids`, and optional JSON-string `extra_metadata`.
- Speaker CRUD is exposed under `/speakers`.
- Background job status is read from `GET /jobs/{job_id}`.
- External workers request a fresh transcript upload ticket from
  `POST /worker/jobs/{job_id}/transcript-upload` using their active lease token.
- External workers require an absolute HTTPS `AYQM_API_URL`. The Runpod image
  requires a CUDA 12.8-compatible host and sends an explicit `AYQM-Worker/1.0`
  User-Agent so Cloudflare Browser Integrity Check does not return error 1010.
- Trivia extraction requires a completed diarized transcript, full speaker-label
  mapping, and a Gemini/Google API key in the webapp process environment.
- Diarization also requires `HF_TOKEN`, accepted Pyannote model terms, and a
  compatible local Pyannote/TorchCodec/FFmpeg setup.

## Vector Search Roadmap
Embeddings are deferred. When ready, choose an embedding provider and fixed vector
dimension, add an embedding column using DuckDB fixed-size arrays, and create a
DuckDB VSS/HNSW index for nearest-neighbor search over trivia items.

## Current Progress
- [x] FastAPI backend scaffolded.
- [x] DuckDB schema and repositories added.
- [x] Upload, processing, transcript, trivia, and job endpoints added.
- [x] Global speaker CRUD, episode speaker selection, and speaker mapping
      endpoints added.
- [x] Backend tests added with mocked transcription/extraction.
- [x] Single-admin authentication and protected administrative APIs added.
- [x] Episode publishing, public reads, metadata editing, and trivia editing,
      deletion, and AI rephrasing added.
- [x] R2 direct uploads, RSS import, leased external workers, portable backups,
      and Cloudflare/Railway deployment configuration added.

## Next Planned Work: Episode Administration
- [ ] Add `PATCH /episodes/{episode_id}/publication` for explicit
      Publish/Unpublish actions. Publishing does not require trivia, but both
      actions are blocked while an episode job is queued or running.
- [ ] Add `active_job` to admin episode responses so processing controls remain
      safe after a browser refresh. Public schemas must continue to omit jobs.
- [ ] Add permanent `DELETE /episodes/{episode_id}`. Block deletion during an
      active job; remove episode-owned database rows, source audio, transcript
      artifacts, and local caches, but retain `gemini_usage` as cost history.
- [ ] Put Publish/Unpublish beside Extract trivia on Overview and remove the
      publication checkbox from Details. Metadata in Overview remains read-only.
- [ ] Put Delete episode in an Overview danger zone. Warn that audio,
      transcript, trivia, mappings, and processing history will be permanently
      removed, and require the exact episode title before enabling deletion.
- [ ] Cover backend cascade/storage behavior and frontend mutation, confirmation,
      active-job, navigation, and query-invalidation flows with focused tests.
