# Local Transcription Runbook

Use this workflow for Episode 144 and newer weekly episodes. Production keeps
the audio, transcript artifact, and DuckDB records; the Mac only acts as a
trusted external worker for the queued transcription job.

## Prerequisites

1. Production Railway API is deployed with:

```dotenv
AYQM_STORAGE_BACKEND=r2
AYQM_EXTERNAL_TRANSCRIPTION_WORKER=true
AYQM_WORKER_TOKEN=<separate-random-worker-secret>
```

2. The production frontend is deployed with `VITE_API_BASE_URL` pointing at the
   production API.
3. Your Hugging Face account has accepted the terms for
   `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0`.
4. Your Mac has the repo dependencies installed:

```sh
/Users/adityasrivastava/.local/bin/uv sync
```

5. Keep these secrets outside git:
   - `HF_TOKEN`: Hugging Face read token.
   - `AYQM_WORKER_TOKEN`: same value configured in Railway.

## Weekly Episode Workflow

1. In production admin, add the new episode:
   - Use `/admin/imports` if the episode is already available in the RSS feed.
   - Otherwise use `/admin/episodes/new` to upload the audio and metadata.
   - Select the expected episode speakers before transcription.
   - Keep the episode hidden from the public site while processing.

2. Open the episode Overview tab and click **Transcribe**.

   With `AYQM_EXTERNAL_TRANSCRIPTION_WORKER=true`, this creates a queued job in
   production DuckDB. Railway does not run WhisperX itself.

3. From the repo root on the Mac, claim and process one queued job:

```sh
HF_TOKEN='<hugging-face-token>' /Users/adityasrivastava/.local/bin/uv run ayqm-worker \
  --api-url https://api.example.com \
  --token '<worker-token>' \
  --worker-name aditya-mac \
  --model large-v3 \
  --device cpu \
  --compute-type int8 \
  --batch-size 16 \
  --once
```

   Replace `https://api.example.com` with the live API origin and
   `<worker-token>` with Railway's `AYQM_WORKER_TOKEN`.

4. Watch the worker logs for the normal sequence:
   - job claimed
   - source audio downloaded from R2
   - transcription started
   - transcript uploaded to R2
   - job completed

5. Back in admin, confirm the episode transcription status is completed.

6. Open **Speaker mapping**, listen to the generated sample clips, and map every
   diarization label to one of the selected episode speakers.

7. Return to Overview and click **Extract trivia**.

8. Review and edit extracted trivia.

9. Click **Show on website** when the episode is ready for public visitors.

## How Deployment Works

No transcript file is manually copied to the live server.

The local worker uses authenticated production worker APIs:

1. `POST /worker/jobs/claim` leases a queued job and returns a short-lived R2
   audio download URL.
2. The Mac writes `transcript.json` locally in a temporary directory.
3. `POST /worker/jobs/{job_id}/transcript-upload` returns a short-lived R2
   upload URL for `artifacts/{episode_id}/transcript.json`.
4. `POST /worker/jobs/{job_id}/complete` tells Railway to validate the uploaded
   artifact and save it into production DuckDB.

After that, production admin can generate speaker samples, save mappings, run
Gemini trivia extraction, and publish the episode. The public site reads only
published data from the live API.

Code deployments remain separate from transcription:

1. Push backend or frontend changes to the production branch.
2. Railway redeploys the FastAPI API from `Dockerfile`.
3. Cloudflare Pages rebuilds the frontend from `frontend`.
4. Pull latest locally before running the worker if worker code changed.

## Operating Notes

- `--once` is the weekly default because it processes exactly one episode.
- Remove `--once` only when you intentionally want the Mac to drain all queued
  transcription jobs.
- CPU/int8 is the safe default for macOS. Keep it as the fallback command.
- Benchmark faster local settings separately after the weekly workflow is
  proven. Runpod used CUDA/NVIDIA; Mac acceleration has different
  WhisperX/Pyannote/Torch compatibility constraints.
- If the worker fails, the job is marked failed in admin. Re-click
  **Transcribe** after fixing the local issue to create a fresh job.
- Do not commit transcripts, audio files, local databases, `.env`, or generated
  artifacts.
