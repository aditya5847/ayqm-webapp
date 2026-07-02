# ayqm-webapp

FastAPI and React application for podcast ingestion, transcription, speaker
mapping, trivia extraction, editorial administration, and published episode
delivery.

## Setup

```sh
/Users/adityasrivastava/.local/bin/uv sync
```

Create `.env` from `.env.example`. Generate the single-admin password hash and
session secret:

```sh
/Users/adityasrivastava/.local/bin/uv run python -c "from argon2 import PasswordHasher; print(PasswordHasher().hash('YOUR_PASSWORD'))"
/Users/adityasrivastava/.local/bin/uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set the results as `AYQM_ADMIN_PASSWORD_HASH` and `AYQM_SESSION_SECRET`. Keep
`AYQM_SESSION_COOKIE_SECURE=false` for local HTTP; set it to `true` behind
production HTTPS. Do not commit `.env`.

## Run

```sh
/Users/adityasrivastava/.local/bin/uv run uvicorn backend.app.main:app --reload --port 8001
```

The API is available at `http://127.0.0.1:8001`; interactive documentation is
at `http://127.0.0.1:8001/docs`. From `frontend/`, `npm run dev` starts Vite and
proxies `/api` to this address.

## Authentication

All episode, speaker, job, transcript, mapping, and trivia administration routes
require the signed admin cookie. Log in and store it for curl:

```sh
curl -c /tmp/ayqm-cookie -X POST http://127.0.0.1:8001/auth/login \
  -H 'content-type: application/json' \
  -d '{"password":"YOUR_PASSWORD"}'
```

Pass `-b /tmp/ayqm-cookie` to protected requests. Sessions last seven days by
default. `GET /auth/session` reports login state and `POST /auth/logout` clears
the cookie.

## API

Public, unauthenticated reads expose only published content:

- `GET /public/episodes`
- `GET /public/episodes/{episode_id}`
- `GET /public/episodes/{episode_id}/trivia`
- `GET /public/trivia?limit=24&offset=0`

Administrative editing includes:

- `PATCH /episodes/{episode_id}` for metadata, selected speakers, and publication
- `PATCH /trivia/{trivia_id}` and `DELETE /trivia/{trivia_id}`
- `POST /trivia/{trivia_id}/rephrase` for a non-persisted Gemini suggestion

Starting trivia extraction or full processing returns the episode to draft
before replacing trivia.

### Upload and processing

Create a speaker:

```sh
curl -b /tmp/ayqm-cookie -X POST http://127.0.0.1:8001/speakers \
  -H 'content-type: application/json' \
  -d '{"name":"Ada"}'
```

Upload fields are `file`, `episode_title`, integer `episode_number`, optional
`episode_description`, optional `published_at`, optional `source_url`, required
JSON-string `speaker_ids`, and optional JSON-string `extra_metadata`.

```sh
curl -b /tmp/ayqm-cookie -X POST http://127.0.0.1:8001/episodes \
  -F 'file=@/absolute/path/to/episode.mp3;type=audio/mpeg' \
  -F 'episode_title=Episode Title' \
  -F 'episode_number=1' \
  -F 'speaker_ids=["SPEAKER_ID_1","SPEAKER_ID_2"]'
```

The diarized workflow is:

1. `POST /episodes/{episode_id}/transcribe`.
2. Poll `GET /jobs/{job_id}`.
3. Read `GET /episodes/{episode_id}/speaker-labels` and listen to its cached,
   maximum-three-second sample URLs.
4. Save every label with `PUT /episodes/{episode_id}/speaker-mapping`.
5. Start `POST /episodes/{episode_id}/extract-trivia`.
6. Read `GET /episodes/{episode_id}/trivia`.

Trivia extraction is blocked until every detected label is mapped. API consumers
must use top-level `asker` as the resolved identity; nested
`speaker_diarization.asker_speaker` is raw model output.

## Test

```sh
/Users/adityasrivastava/.local/bin/uv run pytest
cd frontend && npm test && npm run build
```

Tests mock transcription and Gemini integrations. A local Pyannote/TorchCodec/
FFmpeg configuration is still required for real diarized transcription, along
with `HF_TOKEN` and accepted model terms. Trivia extraction and rephrasing need
`GEMINI_API_KEY` or `GOOGLE_API_KEY`.

Uploaded audio is stored under `data/uploads/{episode_id}/`; generated artifacts
are stored under `data/episodes/{episode_id}/`. Do not commit `data/`, generated
artifacts, DuckDB files, or `.env`.
