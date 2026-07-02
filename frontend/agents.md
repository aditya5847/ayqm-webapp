# Frontend Context

## Purpose
The React frontend has two distinct experiences:
- A public editorial podcast site for published episodes and trivia.
- A compact, authenticated admin workspace for podcast operations.

The visual system is based on `references/Logo.png` and
`references/Podcast Thumbnail.jpg`: black ink, white space, comic-style borders,
and red, cyan, yellow, and orange accents. Keep public pages expressive and
editorial; keep admin pages dense and operational.

## Stack and Commands
- React 19, TypeScript, Vite, React Router, TanStack Query, and Lucide icons.
- Run `npm test` and `npm run build` from `frontend/`.
- Run `npm run dev`; Vite proxies `/api` to FastAPI at `127.0.0.1:8001`.

## Routes
- Public: `/`, `/episodes`, `/episodes/:episodeId`, `/trivia`, and the static
  researched `/about` page.
- Admin login: `/admin/login`.
- Admin: `/admin/episodes`, `/admin/episodes/new`,
  `/admin/episodes/:episodeId`, and `/admin/speakers`.
- Keep public and admin layouts separate. Public routes must not expose admin
  metadata, filesystem paths, raw diarization labels, or unpublished content.

## API Expectations
- Public reads use `/public/episodes`, `/public/episodes/{episode_id}`,
  `/public/episodes/{episode_id}/trivia`, and `/public/trivia`.
- Admin sessions use `/auth/login`, `/auth/session`, and `/auth/logout` with an
  HTTP-only cookie. Frontend requests send credentials.
- Existing upload, processing, job, speaker, transcript, and mapping APIs retain
  their current contracts.
- Episode updates use `PATCH /episodes/{episode_id}` with metadata,
  `speaker_ids`, and episode-level `is_published`.
- Trivia updates use `PATCH /trivia/{trivia_id}`; deletion uses
  `DELETE /trivia/{trivia_id}`; AI suggestions use
  `POST /trivia/{trivia_id}/rephrase`. Suggestions are never saved without an
  explicit user action.
- Treat only `404`, `405`, and `501` from planned endpoints as unsupported and
  show the view-specific Coming Soon panel. Display other errors normally.

## Existing Workflow Rules
- Upload fields are `file`, `episode_title`, integer `episode_number`, optional
  `episode_description`, optional `published_at`, optional `source_url`, JSON
  `speaker_ids`, and optional JSON `extra_metadata`.
- Mandatory upload fields are visibly marked with `*` and use native required
  validation where applicable.
- Before trivia extraction, map every detected label from
  `/episodes/{episode_id}/speaker-labels` to a selected episode speaker.
- Use top-level trivia `asker` for identity. Never present
  `speaker_diarization.asker_speaker` as a real speaker.
- Public listening links use `source_url`; do not expose uploaded audio.

## Design and Testing
- Use supplied raster assets and Lucide icons. Do not substitute generated SVG
  artwork for the podcast identity.
- Preserve readable text, stable controls, keyboard access, and responsive
  layouts down to 320px. Avoid nested cards and decorative gradients.
- Cover routing, loading/empty/error states, Coming Soon handling, answer reveal,
  required upload fields, and admin mutation flows with focused tests.
