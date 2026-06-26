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
- Transcription diarizes by default and requires `HF_TOKEN` on the backend.
- Before trivia extraction, show `/episodes/{episode_id}/speaker-labels` so the
  user can listen to max-3-second sample clips and map labels like `SPEAKER_00`
  to selected speakers.
- Trivia extraction is blocked until all detected speaker labels are mapped.
- Trivia items may include top-level `asker`, which is the resolved real
  speaker. Do not display `speaker_diarization.asker_speaker` as the speaker ID;
  that nested value is the raw label such as `SPEAKER_00`.
