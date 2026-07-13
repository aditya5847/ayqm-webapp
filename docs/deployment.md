# Production Deployment

This runbook deploys the React frontend on Cloudflare Pages, the single-process
FastAPI/DuckDB service on Railway, private objects on Cloudflare R2, and
transcription workers on Runpod or a trusted Mac.

## 1. Create Cloudflare resources

1. Add the domain to Cloudflare without changing nameservers yet.
2. Review the imported DNS records, especially MX, SPF, DKIM, and DMARC records.
3. Create a private R2 bucket named `ayqm-production`.
4. Create an R2 API token limited to object read/write for that bucket.
5. Record the S3 endpoint, access key ID, secret access key, and bucket name.
6. Add an R2 CORS rule allowing `PUT`, `GET`, and `HEAD` from the production
   frontend origin and the `Content-Type` header.
7. Add lifecycle rules deleting `backups/daily/` after 30 days and
   `backups/monthly/` after 365 days. Audio and `artifacts/` have no expiry.

## 2. Deploy the Railway API

1. Create a Railway project from this GitHub repository using `Dockerfile`.
2. Attach one persistent volume at `/data`. Keep the service at one replica;
   `uvicorn` is explicitly configured with one worker.
3. Start with a clean volume. Do not upload `data/ayqm.duckdb` from development.
4. Set the following variables, replacing all placeholders:

```dotenv
AYQM_ENVIRONMENT=production
AYQM_DATABASE_PATH=/data/ayqm.duckdb
AYQM_UPLOAD_ROOT=/tmp/ayqm/uploads
AYQM_EPISODE_ROOT=/tmp/ayqm/episodes
AYQM_ALLOWED_ORIGINS=https://example.com,https://www.example.com
AYQM_ADMIN_PASSWORD_HASH=<argon2-hash>
AYQM_SESSION_SECRET=<random-48-byte-secret>
AYQM_SESSION_COOKIE_SECURE=true
AYQM_STORAGE_BACKEND=r2
AYQM_R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
AYQM_R2_BUCKET=ayqm-production
AYQM_R2_ACCESS_KEY_ID=<r2-access-key>
AYQM_R2_SECRET_ACCESS_KEY=<r2-secret-key>
AYQM_EXTERNAL_TRANSCRIPTION_WORKER=true
AYQM_WORKER_TOKEN=<separate-random-worker-secret>
AYQM_BACKUP_ENABLED=true
AYQM_BACKUP_HOUR_UTC=2
AYQM_GEMINI_MODEL=gemini-3.1-flash-lite
AYQM_GEMINI_BUDGET_USD=5
GEMINI_API_KEY=<paid-project-key>
```

5. Enable Railway daily volume backups. Keep the independent R2 export enabled.
6. Generate a Railway custom domain for `api.example.com` and add its CNAME in
   Cloudflare. Verify `/health/live` and `/health/ready` before continuing.

## 3. Deploy Cloudflare Pages

1. Connect the GitHub repository to Pages and set the root directory to
   `frontend`.
2. Use `npm ci && npm run build` as the build command and `dist` as the output.
3. Set `VITE_API_BASE_URL=https://api.example.com`.
4. Attach the apex domain and `www` domain, redirecting `www` to the apex.
5. Sign in to `/admin/login` and test a small direct upload before importing RSS.

## 4. Move DNS to Cloudflare

1. If DNSSEC is enabled at the registrar, disable it temporarily.
2. Replace the registrar nameservers with the two assigned by Cloudflare.
3. Wait for the Cloudflare zone to become active and verify the root, `www`, and
   `api` hostnames over HTTPS.
4. Re-enable DNSSEC in Cloudflare.

The registrar still owns and renews the domain; only DNS resolution moves.

## 5. Import the podcast archive

1. Open `/admin/imports` and run **Preview feed**. Confirm the discovered count.
2. Run **Import feed**. The importer reads the configured Anchor RSS feed,
   processes oldest first, and copies each enclosure to private R2 storage.
3. Re-running the import is safe: RSS GUID is unique, existing objects are not
   downloaded again, manual titles/descriptions are not overwritten, and
   missing or changed per-episode artwork is copied into R2.
4. For the measured feed baseline, verify 148 records, Episodes 1 through 143,
   four mini episodes, one announcement, and about 11.55 GB of source audio.
   Use the live feed's higher count if new episodes have appeared.
5. Review the episode list before publishing metadata.

## 6. Run the historical GPU backfill

Push the worker changes to `main`, then run **Publish transcription worker
image** from the GitHub Actions tab. The workflow builds `Dockerfile.worker` for
`linux/amd64` and publishes both `main` and commit-specific `sha-*` tags under:

```text
ghcr.io/aditya5847/ayqm-webapp-worker
```

Open the package settings after its first successful build and make the package
public. Deploy the immutable `sha-*` tag shown in the workflow output rather
than `main`. Before creating the Pod, accept the Hugging Face conditions for
both `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0`, then
create a read token.

Create two Runpod secrets named `ayqm_worker_token` and `huggingface_token`.
The first must contain the same token as Railway's `AYQM_WORKER_TOKEN`; the
second contains the Hugging Face read token. Create a private NVIDIA GPU Pod
template with no exposed ports and configure these environment variables:

```dotenv
AYQM_API_URL=https://api.example.com
AYQM_WORKER_TOKEN={{ RUNPOD_SECRET_ayqm_worker_token }}
HF_TOKEN={{ RUNPOD_SECRET_huggingface_token }}
HF_HOME=/workspace/huggingface
AYQM_LOG_LEVEL=INFO
```

Use one on-demand RTX 4090 with 24 GB VRAM, at least 40 GB of container disk,
and a 50 GB volume mounted at `/workspace`. The volume keeps the Hugging Face
model cache across Pod stops. Source audio and transcripts use temporary local
storage because the worker transfers them between R2 and the Pod.

Queue one short episode before deploying the pilot. The worker image already
defines its entrypoint, so set only these command arguments in the template:

```sh
--worker-name runpod-pilot --model large-v3 --device cuda --compute-type float16 --batch-size 16 --once
```

Confirm the logs show the job being claimed, downloaded, transcribed, uploaded,
and completed. The admin status must move from `queued` to `running` and then
`succeeded`. If CUDA runs out of memory, reduce the batch size to 8 and then 4.

For the full backfill, use:

```sh
--worker-name runpod-backfill --model large-v3 --device cuda --compute-type float16 --batch-size 16 --idle-timeout-seconds 300
```

The worker leases one episode at a time, renews its lease, obtains a fresh R2
upload URL after transcription, uploads the transcript, and asks the API to
commit it to DuckDB. Check measured throughput and spend after the first three
episodes; stop if the projection exceeds the agreed $30 cap. When the queue is
empty, stop the Pod to release the GPU even if the worker process has exited.
Terminate the Pod after the backfill to delete its billable volume.

The worker sends an explicit `AYQM-Worker/1.0` User-Agent so Cloudflare Browser
Integrity Check does not reject its authenticated API requests with error 1010.

## 7. Review and extract trivia

1. Work chronologically in the admin episode list.
2. Correct the episode speaker roster, then map every diarization label using
   its sample clips.
3. Start trivia extraction only after mapping is complete.
4. Gemini runs serially in the API, retries rate limits, records token/cost
   usage, deduplicates by transcript hash/model/prompt version, and stops once
   the application ledger reaches `$AYQM_GEMINI_BUDGET_USD`.
5. Review and edit trivia before publishing each episode. Publish in manageable
   chronological batches while the remaining backfill continues.

## 8. Process future episodes from the Mac

Use the detailed [local transcription runbook](local-transcription.md) for
Episode 144 and newer weekly episodes.

Upload or import the episode through production admin, click **Transcribe**, and
then run one queued job locally:

```sh
export AYQM_API_URL='https://api.example.com'
export AYQM_WORKER_TOKEN='<worker-token>'
export HF_TOKEN='<token>'
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/ffmpeg@7/lib

/Users/adityasrivastava/.local/bin/uv run ayqm-worker \
  --worker-name aditya-mac \
  --model medium \
  --device cpu \
  --compute-type int8 \
  --batch-size 4 \
  --once
```

The default local worker profile is CPU/int8 with `medium` and batch size 4.
Use `--model small` only for a faster smoke test. Reserve `large-v3` for
Runpod/CUDA or an intentional overnight local run. Leave off `--once` to drain
the queue continuously. The worker downloads source audio from R2, uploads the
transcript artifact back to R2, and asks the Railway API to commit the
transcript to production DuckDB; no manual transcript deployment is required.

## 9. Backup and restore check

Railway snapshots provide short-term volume recovery. The application also
runs `CHECKPOINT` and `EXPORT DATABASE` under its database lock, packages the
portable Parquet export, and uploads daily/monthly archives to R2.

Before launch, download one archive into an isolated environment, extract it,
create a new empty DuckDB file, run `IMPORT DATABASE '<export-directory>'`, and
compare counts for episodes, speakers, jobs, transcripts, and trivia. Repeat
this restore drill monthly and before DuckDB version upgrades.
