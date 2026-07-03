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
   downloaded again, and manual titles/descriptions are not overwritten.
4. For the measured feed baseline, verify 148 records, Episodes 1 through 143,
   four mini episodes, one announcement, and about 11.55 GB of source audio.
   Use the live feed's higher count if new episodes have appeared.
5. Review the episode list before publishing metadata.

## 6. Run the historical GPU backfill

Build and publish `Dockerfile.worker`, then start an on-demand Runpod Pod using
the image. Supply `HF_TOKEN` after accepting the required Pyannote model terms.
Benchmark a mini, an average episode, and a long multi-speaker episode first.

Create the Pod from a custom template with no exposed ports and configure these
environment variables (use Runpod secrets for token values):

```dotenv
AYQM_API_URL=https://api.example.com
AYQM_WORKER_TOKEN=<same value configured on Railway>
HF_TOKEN=<Hugging Face read token>
HF_HOME=/workspace/huggingface
```

An RTX 4090 with 24 GB VRAM is a suitable starting point. Allocate at least
40 GB of container disk. A volume mounted at `/workspace` is optional, but it
keeps the Hugging Face model cache across Pod stops and avoids downloading the
models again. It does not need to hold source audio or transcripts because the
worker downloads each source from R2, uses temporary local storage, and uploads
the result to R2.

The worker image already defines its entrypoint. Set only these command
arguments in the Runpod template:

```sh
--worker-name runpod-pilot \
  --model large-v3 \
  --device cuda \
  --compute-type float16 \
  --batch-size 16 \
  --max-jobs 3
```

Check measured throughput and Runpod spend after the three-episode pilot. Do not
continue if the projection exceeds the agreed $30 cap. Remove `--max-jobs 3`
and change the worker name before starting the full backfill. The worker leases one
episode at a time, renews its lease, uploads the transcript to R2, and asks the
API process to commit it to DuckDB.

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

Upload through the admin UI, then run one queued job locally:

```sh
HF_TOKEN=<token> /Users/adityasrivastava/.local/bin/uv run ayqm-worker \
  --api-url https://api.example.com \
  --token '<worker-token>' \
  --worker-name aditya-mac \
  --model large-v3 \
  --device cpu \
  --compute-type int8 \
  --batch-size 16 \
  --once
```

The default remains CPU/int8 for macOS safety. Leave off `--once` to drain the
queue continuously.

## 9. Backup and restore check

Railway snapshots provide short-term volume recovery. The application also
runs `CHECKPOINT` and `EXPORT DATABASE` under its database lock, packages the
portable Parquet export, and uploads daily/monthly archives to R2.

Before launch, download one archive into an isolated environment, extract it,
create a new empty DuckDB file, run `IMPORT DATABASE '<export-directory>'`, and
compare counts for episodes, speakers, jobs, transcripts, and trivia. Repeat
this restore drill monthly and before DuckDB version upgrades.
