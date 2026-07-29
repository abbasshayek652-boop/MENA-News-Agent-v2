# MENA News Agent

Ingests RSS feeds from ~45 MENA-region news sources, ranks and dedupes them,
generates a bilingual (Arabic/English) dialectical analysis report via
Claude (or a self-hosted Ollama model), delivers it to Telegram, and keeps a
web dashboard of past runs.

## Architecture

```
RSS feeds (config/sources.yaml)
        │  round-robin sampled, per-source capped (rss_ingest.py)
        ▼
Full-text extraction (fetch_extract.py)  ── rejects bot-blocked / thin pages
        ▼
Dedupe + tier-weighted ranking (dedupe_rank.py)
        ▼
LLM analysis (report_writer.py + llm_client.py)  ── Claude by default, Ollama optional
        │                                             falls back to a clearly-labeled
        │                                             placeholder if the LLM is down
        ▼
Telegram delivery (telegram_sender.py)  ── HTML-formatted, auto-split into multiple
        │                                    messages if the report is long
        ▼
Run history storage (store.py)  ── local disk or GCS
        ▼
Dashboard (server.py + templates/)  ── lists past runs, shows full reports
```

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY, TELEGRAM_*, etc.

pytest -q                          # run tests
python3 main.py once --dry-run     # run the pipeline once, no LLM calls
python3 main.py serve              # start the API + dashboard on :8080
```

Then visit `http://localhost:8080/dashboard`.

### Validating your RSS sources

RSS feeds break/move without notice. Run this periodically (from anywhere
with normal internet access):

```bash
python3 scripts/validate_sources.py
```

It reports exactly which of your configured sources are alive and how many
entries each returns — fix or remove the ones that fail.

## Configuration

See `.env.example` for the full list. Key ones:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `anthropic` (default) or `ollama` |
| `ANTHROPIC_API_KEY` | Required if using Claude |
| `DRY_RUN` | `1` = always use the placeholder report, no LLM calls |
| `SEND_TELEGRAM` | `1` = send to Telegram by default on every run |
| `STORAGE_BACKEND` | `local` (default, ephemeral on Cloud Run) or `gcs` (durable) |
| `API_SECRET_TOKEN` | If set, required to call `POST /run` or view `/dashboard` |

## Deploying to Cloud Run (via GitHub Actions)

Every push to `main` automatically builds and deploys via
`.github/workflows/deploy.yml`. One-time setup:

### 1. Enable required GCP APIs

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com
```

### 2. Create a deploy service account

```bash
gcloud iam service-accounts create mena-agent-deployer \
  --display-name="MENA Agent GitHub Actions Deployer"

PROJECT_ID=$(gcloud config get-value project)
SA_EMAIL="mena-agent-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

for role in roles/run.admin roles/iam.serviceAccountUser roles/cloudbuild.builds.editor \
            roles/artifactregistry.writer roles/secretmanager.secretAccessor roles/storage.admin; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" --role="$role"
done

gcloud iam service-accounts keys create sa-key.json --iam-account="$SA_EMAIL"
```

### 3. Create secrets in Secret Manager

```bash
echo -n "your-telegram-bot-token"   | gcloud secrets create telegram-bot-token   --data-file=-
echo -n "your-telegram-chat-id"     | gcloud secrets create telegram-chat-id     --data-file=-
echo -n "your-anthropic-api-key"    | gcloud secrets create anthropic-api-key    --data-file=-
echo -n "some-long-random-string"   | gcloud secrets create api-secret-token     --data-file=-
```

### 4. Add GitHub repository secrets

In your GitHub repo → **Settings → Secrets and variables → Actions**, add:
- `GCP_SA_KEY` — the full contents of `sa-key.json` from step 2
- `GCP_PROJECT_ID` — your GCP project ID

Then delete `sa-key.json` locally — it's now stored securely in GitHub.

### 5. Push to `main`

```bash
git add .
git commit -m "Initial commit"
git push origin main
```

GitHub Actions runs the test suite, then builds and deploys to Cloud Run
automatically. Check the **Actions** tab on GitHub for progress; the last
step prints your service URL.

### 6. Set up scheduled runs (optional)

```bash
SERVICE_URL="$(gcloud run services describe mena-news-agent --region us-central1 --format='value(status.url)')"

gcloud scheduler jobs create http mena-agent-daily \
  --schedule="0 8 * * *" \
  --uri="${SERVICE_URL}/run?dry_run=false&send_telegram=true" \
  --http-method=POST \
  --headers="X-API-KEY=your-api-secret-token" \
  --location=us-central1
```

## Testing

```bash
pytest -q
```

19 tests cover RSS round-robin sampling, tier-weighted ranking, extraction
filtering, Telegram formatting/chunking, LLM fallback behavior, run storage,
and a full pipeline integration test.

## Notes on data persistence

By default (`STORAGE_BACKEND=local`), run history is written to `/tmp` on
the Cloud Run instance — this is **ephemeral** and resets whenever a new
revision deploys or the instance is recycled. For durable history across
deploys, set `STORAGE_BACKEND=gcs` and `GCS_BUCKET=your-bucket-name`, and
grant the Cloud Run service account `roles/storage.objectAdmin` on that
bucket.
