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
   - `AYQM_API_URL`: production API origin, including `https://`.
   - `HF_TOKEN`: Hugging Face read token.
   - `AYQM_WORKER_TOKEN`: same value configured in Railway.

6. Homebrew FFmpeg libraries must be visible to Python's dynamic loader. On this
   Mac, `torchcodec` imports successfully with:

```sh
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/ffmpeg@7/lib
```

## Weekly Episode Workflow

1. In production admin, add the new episode:
   - Use `/admin/imports` if the episode is already available in the RSS feed.
   - Otherwise use `/admin/episodes/new` to upload the audio and metadata.
   - Select the expected episode speakers before transcription.
   - Keep the episode hidden from the public site while processing.

2. Open the episode Overview tab and click **Transcribe**.

   With `AYQM_EXTERNAL_TRANSCRIPTION_WORKER=true`, this creates a queued job in
   production DuckDB. Railway does not run WhisperX itself.

3. From the repo root on the Mac, export the worker environment:

```sh
export AYQM_API_URL='https://api.example.com'
export AYQM_WORKER_TOKEN='<worker-token>'
export HF_TOKEN='<hugging-face-token>'
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/ffmpeg@7/lib
```

   Replace `https://api.example.com` with the live API origin and
   `<worker-token>` with Railway's `AYQM_WORKER_TOKEN`. The worker also loads
   these values from the repo-root `.env`, but exporting them makes the active
   shell unambiguous.

4. Verify the local worker process can see credentials and load audio
   dependencies:

```sh
/Users/adityasrivastava/.local/bin/uv run python -c "import os, torchcodec; assert os.getenv('AYQM_API_URL'); assert os.getenv('AYQM_WORKER_TOKEN'); assert os.getenv('HF_TOKEN'); print('worker env ok')"
```

5. Claim and process one queued job with the Mac CPU profile:

```sh
/Users/adityasrivastava/.local/bin/uv run ayqm-worker \
  --worker-name aditya-mac \
  --model medium \
  --device cpu \
  --compute-type int8 \
  --batch-size 4 \
  --once
```

   The worker defaults to this `medium`/CPU/int8/batch-4 profile when no model
   or batch size is supplied. Use it to run the weekly Mac transcript.

6. If you need a faster smoke test, temporarily override the model with
   `small`:

```sh
/Users/adityasrivastava/.local/bin/uv run ayqm-worker \
  --worker-name aditya-mac \
  --model small \
  --device cpu \
  --compute-type int8 \
  --batch-size 4 \
  --once
```

   Do not use `large-v3` as the routine Mac CPU profile. Reserve it for
   Runpod/CUDA or an intentional overnight local run after `medium` has proven
   the workflow.

7. Watch the worker logs for the normal sequence:
   - job claimed
   - source audio downloaded from R2
   - transcription started
   - transcript uploaded to R2
   - job completed

8. Back in admin, confirm the episode transcription status is completed.

9. Open **Speaker mapping**, listen to the generated sample clips, and map every
   diarization label to one of the selected episode speakers.

10. Return to Overview and click **Extract trivia**.

11. Review and edit extracted trivia.

12. Click **Show on website** when the episode is ready for public visitors.

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
- CPU/int8 with `medium` and batch size 4 is the standard Mac profile. Use
  `small` only for a faster smoke test.
- Benchmark faster local settings separately after the weekly workflow is
  proven. Runpod used CUDA/NVIDIA; Mac acceleration has different
  WhisperX/Pyannote/Torch compatibility constraints.
- If the last log line is language detection for the first 30 seconds, the
  worker is in full-file Whisper transcription. On Mac CPU, `large-v3` may look
  stuck for hours; retry with `medium` or `small` before investigating deeper.
- If `torchcodec` or pyannote reports missing `libavutil`, `libavcodec`, or
  other FFmpeg libraries, export
  `DYLD_LIBRARY_PATH=/opt/homebrew/opt/ffmpeg@7/lib` before starting the worker.
- If the worker fails, the job is marked failed in admin. Re-click
  **Transcribe** after fixing the local issue to create a fresh job.
- Do not commit transcripts, audio files, local databases, `.env`, or generated
  artifacts.
