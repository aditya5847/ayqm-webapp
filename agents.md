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
- Default transcription settings should stay macOS-safe: CPU and `int8`.

## Architecture
- Backend code lives in `backend/app`.
- Uploaded audio is stored under `data/uploads/{episode_id}/`.
- Generated transcript/trivia artifacts are stored under
  `data/episodes/{episode_id}/`.
- DuckDB stores episode metadata, jobs, transcripts, and trivia rows.
- Background processing uses FastAPI in-process background tasks for v1.

## Vector Search Roadmap
Embeddings are deferred. When ready, choose an embedding provider and fixed vector
dimension, add an embedding column using DuckDB fixed-size arrays, and create a
DuckDB VSS/HNSW index for nearest-neighbor search over trivia items.

## Current Progress
- [x] FastAPI backend scaffolded.
- [x] DuckDB schema and repositories added.
- [x] Upload, processing, transcript, trivia, and job endpoints added.
- [x] Backend tests added with mocked transcription/extraction.

