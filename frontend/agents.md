# Frontend Context

Frontend work is intentionally deferred. The future frontend should consume the
FastAPI backend endpoints and poll job status via `GET /jobs/{job_id}`.

## API Expectations
- Create speakers through `/speakers` before uploading episodes.
- Upload episodes with multipart form data: `file`, `episode_title`, integer
  `episode_number`, optional `episode_description`, optional `published_at`,
  optional `source_url`, JSON-string `speaker_ids`, and JSON-string
  `extra_metadata`.
- Send `speaker_ids` as an array of ID strings, not speaker objects.
- Episode objects use `episode_title`; do not use `title`, `show_title`, or
  `show_name`.
- Trivia items may include `asker`, which is resolved from diarization speaker
  mappings.
