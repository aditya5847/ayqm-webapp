# AYQM Webapp Agent Guide

This repository contains the AYQM FastAPI/DuckDB backend and the React/Vite
frontend. Treat it as one product: a public podcast/trivia site plus a compact
authenticated admin workspace.

Use the more specific notes in `backend/agents.md` and `frontend/agents.md`
when working deeply in those areas. This root file is the project-wide contract.

## Project Principles

- Preserve DuckDB-backed storage and existing API contracts unless the task
  explicitly requires a schema or contract change.
- Keep generated artifacts, local databases, uploads, transcripts, trivia JSON,
  build outputs, and `.env` files out of commits.
- Do not expose admin-only data on public routes. Public responses must not leak
  filesystem paths, raw diarization labels, jobs, draft state, or unpublished
  episodes/trivia.
- Keep frontend changes consistent with the current retro AYQM style: black ink,
  white space, comic-style borders, and red/cyan/yellow/orange accents.
- Dev-only placeholder content may be used to inspect layout, but it must not
  affect production behavior.
- If the worktree is dirty, assume the changes belong to the user unless you
  made them in the current task.

## Backend Contracts

- Admin APIs are FastAPI routes backed by DuckDB. Public APIs live under
  `/public`.
- All `/episodes`, `/speakers`, `/jobs`, and `/trivia` routes require the
  signed single-admin session cookie. `/health`, `/auth/*`, `/public/*`, and
  docs remain public.
- `GET /episodes` returns a paginated `EpisodePageOut` object with `items`,
  `page`, `page_size`, `total_items`, and `total_pages`.
- `POST /episodes` accepts multipart form data, not JSON. Fields are:
  `file`, `episode_title`, integer `episode_number`, optional
  `episode_description`, optional `published_at`, optional `source_url`, JSON
  string `speaker_ids`, and optional JSON string `extra_metadata`.
- Episode responses use `episode_title`; do not reintroduce old `title`,
  `show_title`, or `show_name` fields.
- Speaker CRUD lives under `/speakers`.
- Speaker label summaries and cached sample clips live under
  `/episodes/{episode_id}/speaker-labels`.
- Episode speaker mappings live under `/episodes/{episode_id}/speaker-mapping`.
- Episode metadata and selected speakers are updated through
  `PATCH /episodes/{episode_id}`. Removing speakers also removes invalid
  mappings and clears or recomputes invalid trivia askers.
- Publication is controlled by `PATCH /episodes/{episode_id}/publication`.
  Publishing is valid with zero trivia. Starting trivia extraction or full
  processing returns the episode to draft.
- `DELETE /episodes/{episode_id}` permanently removes episode speaker
  selections, mappings, transcript, trivia, jobs, and the episode row in one
  transaction. Retain `gemini_usage`.

## Processing And Storage

- Jobs are stored in DuckDB before background work starts and transition through
  `queued`, `running`, `succeeded`, or `failed`.
- Default transcription uses Whisper model `base`, CPU, `int8`, batch size `16`,
  and diarization enabled unless explicitly disabled.
- `HF_TOKEN` is required for default diarized transcription unless diarization is
  disabled or an external transcription worker is configured.
- Trivia extraction requires a completed diarized transcript and complete speaker
  mapping.
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` is required for trivia extraction and
  rephrasing. Keep credentials in local environment configuration; never commit
  them.
- Ignore extractor-provided trivia IDs. Persist trivia IDs as
  `{episode_id}-trivia-{index}`.
- Trivia `asker` is resolved from raw diarization through episode speaker
  mappings. API consumers should use top-level `asker`; raw
  `speaker_diarization.asker_speaker` is model output, not a display identity.
- Local DuckDB defaults to `data/ayqm.duckdb`; local uploads/artifacts live under
  `data/`. Production uses R2 object keys and short-lived presigned URLs.
- RSS imports use `rss_guid` for idempotency. `episode_number` is nullable only
  for announcements; main and mini episodes remain numbered.

## Public Site Behavior

- Public routes are `/`, `/episodes`, `/episodes/:episodeId`, `/trivia`, and
  `/about`.
- The public home page shows podcast cover art on the left and latest episode
  artwork/text on the right.
- The public episode archive is paginated.
- The home page recent-episodes strip must not repeat the latest episode.
- Pagination hides `Previous` on the first page and `Next` on the last page.
- Episode labels must distinguish main episodes, mini episodes, and unnumbered
  announcements without rendering `Episode null`.
- Public listening links use `source_url`; do not expose uploaded audio.
- Public `/trivia` defaults to four random published trivia cards.
- Public trivia search uses `?q=...`, searches only published trivia, returns
  four random matching cards, and refreshes by excluding the current card IDs.
- Public trivia search is keyword-based, case-insensitive, and splits multi-word
  queries into required terms across question, answer, and keywords. It is not
  semantic search.
- The About page guest list is data-driven from public speakers plus published
  episodes. Exclude host names. Guest episode links use `#<episode number>`
  labels.

## Admin Frontend Behavior

- Admin routes include `/admin/login`, `/admin/episodes`,
  `/admin/episodes/new`, `/admin/imports`, `/admin/trivia`,
  `/admin/speakers`, and routed episode tabs under
  `/admin/episodes/:episodeId/{overview,details,speaker-mapping,transcript,trivia}`.
- The bare episode route redirects to `overview`.
- Admin episode list uses pagination with matching controls at the top and
  bottom of the list.
- Admin global trivia search lives at `/admin/trivia`. It searches all trivia,
  including unpublished episodes, and returns paginated results.
- Admin trivia search uses the same keyword behavior as public search, but is
  authenticated and not publication-filtered.
- Upload fields must visibly mark required fields with `*` and use native
  required validation where applicable.
- Episode workspace tabs are routed. Overview is read-only. Details owns
  metadata editing. Transcript defaults to mapped-speaker script blocks with a
  raw JSON alternate. Trivia remains read-only until an item is explicitly
  edited.
- Before trivia extraction, every detected diarization label must be mapped to a
  selected episode speaker.
- Trivia editing uses `PATCH /trivia/{trivia_id}`. Deletion uses
  `DELETE /trivia/{trivia_id}`. AI rephrasing uses
  `POST /trivia/{trivia_id}/rephrase` and never persists without explicit save.
- Treat only `404`, `405`, and `501` from planned endpoints as unsupported and
  show Coming Soon. Display other errors normally.
- Keep public and admin layouts separate. Public navigation must not expose
  admin functionality.

## Frontend Style And Assets

- Use React 19, TypeScript, Vite, React Router, TanStack Query, and Lucide
  icons.
- Use supplied raster assets from `frontend/references/` for podcast identity.
  Do not replace them with generated SVG or alternate brand art.
- Keep public pages expressive and editorial; keep admin pages dense,
  operational, and easy to scan.
- Preserve readable text, keyboard access, stable controls, and responsive
  layouts down to 320px.
- Avoid nested cards, decorative gradients, and UI text that explains obvious
  mechanics.
- Use existing shared components and local patterns before introducing new
  abstractions.

## Verification

- Backend tests: run `/Users/adityasrivastava/.local/bin/uv run pytest` from the
  repo root. Focused backend tests are under `tests/`.
- Frontend tests/build: run `npm test` and `npm run build` from `frontend/`.
- Vite dev server: run `npm run dev` from `frontend/`; it proxies `/api` to
  FastAPI at `127.0.0.1:8001`.
- Backend tests should monkeypatch WhisperX/Gemini or `ayqm-transcribe`
  integration points instead of invoking real external services.
- If a full suite cannot be run, state exactly which checks were run and which
  were skipped.
