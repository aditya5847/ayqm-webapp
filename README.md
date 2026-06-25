# ayqm-webapp

FastAPI backend for uploading podcast episodes, transcribing audio with the local
`ayqm-transcribe` library, extracting trivia, and storing results in DuckDB.

## Setup

```sh
/Users/adityasrivastava/.local/bin/uv sync
```

## Run

```sh
/Users/adityasrivastava/.local/bin/uv run uvicorn backend.app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.
Interactive docs are available at `http://127.0.0.1:8000/docs`.

## API

Create speakers before uploading episodes:

```sh
curl -X POST http://127.0.0.1:8000/speakers \
  -H 'content-type: application/json' \
  -d '{"name":"Ada"}'
```

Upload episodes as multipart form data:

- `file`: audio file
- `episode_title`: required string
- `episode_number`: required integer
- `episode_description`: optional string
- `published_at`: optional datetime
- `source_url`: optional URL
- `speaker_ids`: required JSON array string of existing speaker IDs
- `extra_metadata`: optional JSON object string

Speaker endpoints:

- `GET /speakers`
- `POST /speakers`
- `GET /speakers/{speaker_id}`
- `PATCH /speakers/{speaker_id}`
- `DELETE /speakers/{speaker_id}`

Episode speaker mapping endpoints:

- `GET /episodes/{episode_id}/speaker-mapping`
- `PUT /episodes/{episode_id}/speaker-mapping`

## Test

```sh
/Users/adityasrivastava/.local/bin/uv run pytest
```

## Notes

- `ayqm-transcribe` is configured as an editable local dependency from
  `../ayqm-transcribe`.
- Background jobs are in-process FastAPI background tasks. They are suitable for
  local development, not durable production processing.
- Embeddings and DuckDB vector search are intentionally deferred. Trivia is
  stored in normalized tables now so embeddings can be added later.
