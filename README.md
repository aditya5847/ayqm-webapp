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

List speakers:

```sh
curl http://127.0.0.1:8000/speakers
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

- `GET /episodes/{episode_id}/speaker-labels`
- `GET /episodes/{episode_id}/speaker-labels/{label}/sample`
- `GET /episodes/{episode_id}/speaker-mapping`
- `PUT /episodes/{episode_id}/speaker-mapping`

Transcription uses diarization by default. The normal flow is:

1. Upload an episode with selected `speaker_ids`.
2. Start transcription with `POST /episodes/{episode_id}/transcribe`.
3. Read `GET /episodes/{episode_id}/speaker-labels` to show detected labels,
   transcript snippets, and cached MP3 sample clips. Each returned sample has a
   `sample_clip_url`; the label-level `sample_clip_url` points to the first
   sample for compatibility. Clips are stored per episode under
   `data/episodes/{episode_id}/speaker_samples/` and are capped at 3 seconds.
4. Save the label-to-speaker mapping with
   `PUT /episodes/{episode_id}/speaker-mapping`.
5. Start trivia extraction with
   `POST /episodes/{episode_id}/extract-trivia`.

Trivia extraction is blocked until every detected speaker label has been mapped.

### Full curl workflow

Upload an episode:

```sh
curl -X POST http://127.0.0.1:8000/episodes \
  -F 'file=@/absolute/path/to/episode.mp3;type=audio/mpeg' \
  -F 'episode_title=Episode Title' \
  -F 'episode_number=1' \
  -F 'episode_description=Optional description' \
  -F 'speaker_ids=["SPEAKER_ID_1","SPEAKER_ID_2"]' \
  -F 'extra_metadata={"source":"manual_test"}'
```

Start diarized transcription:

```sh
curl -X POST http://127.0.0.1:8000/episodes/EPISODE_ID/transcribe \
  -H 'content-type: application/json' \
  -d '{}'
```

Poll job status:

```sh
curl http://127.0.0.1:8000/jobs/JOB_ID
```

Fetch speaker labels and sample clips:

```sh
curl http://127.0.0.1:8000/episodes/EPISODE_ID/speaker-labels
```

Each label includes sample URLs like:

```text
/episodes/EPISODE_ID/speaker-labels/SPEAKER_00/samples/0
/episodes/EPISODE_ID/speaker-labels/SPEAKER_00/samples/1
```

Save the speaker mapping after listening to the clips:

```sh
curl -X PUT http://127.0.0.1:8000/episodes/EPISODE_ID/speaker-mapping \
  -H 'content-type: application/json' \
  -d '{"mappings":{"SPEAKER_00":"SPEAKER_ID_1","SPEAKER_01":"SPEAKER_ID_2"}}'
```

Extract trivia:

```sh
curl -X POST http://127.0.0.1:8000/episodes/EPISODE_ID/extract-trivia \
  -H 'content-type: application/json' \
  -d '{}'
```

Read trivia:

```sh
curl http://127.0.0.1:8000/episodes/EPISODE_ID/trivia
```

Use the top-level `asker` object as the resolved speaker identity. The nested
`speaker_diarization.asker_speaker` field is the raw diarization label such as
`SPEAKER_00`.

## Test

```sh
/Users/adityasrivastava/.local/bin/uv run pytest
```

## Notes

- `ayqm-transcribe` is configured as an editable local dependency from
  `../ayqm-transcribe`.
- Background jobs are in-process FastAPI background tasks. They are suitable for
  local development, not durable production processing.
- Diarization requires `HF_TOKEN`, accepted Pyannote model terms, and a local
  Pyannote/TorchCodec/FFmpeg stack that can decode audio.
- Gemini trivia extraction requires `GEMINI_API_KEY` or `GOOGLE_API_KEY` in the
  server process environment.
- Embeddings and DuckDB vector search are intentionally deferred. Trivia is
  stored in normalized tables now so embeddings can be added later.
