# Auguspay Deployment Guide

Pick one of three options. **Fly.io is the recommended pick** for this app — it gives you a persistent volume on the free tier, the SSE stream works without quirks, and Mumbai region is available.

---

## Option 1 — Fly.io (recommended, ~5 minutes, free)

Why: free, India region, persistent disk for SQLite, no cold-start issues for SSE, simple CLI.

### One-time setup

```powershell
# install flyctl
iwr https://fly.io/install.ps1 -useb | iex

# sign up (opens browser)
flyctl auth signup
```

### Deploy

```powershell
cd C:\Users\kchotiya\Desktop\Codeforces\AugusPayFinal

# 1. pick a unique app name (edit fly.toml first if you want)
flyctl launch --copy-config --no-deploy --name auguspay-<your-suffix> --region bom

# 2. create the 1 GB volume that will hold auguspay.db
flyctl volumes create auguspay_data --size 1 --region bom

# 3. set a strong session secret (one-time)
flyctl secrets set SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# 4. ship it
flyctl deploy
```

You'll get a URL like `https://auguspay-<suffix>.fly.dev`. Open `/merchant/`, register, you're live.

### Useful follow-ups

```powershell
flyctl logs                          # tail logs
flyctl ssh console                   # shell into the VM (debug SQLite, etc.)
flyctl scale count 1                 # always-on (kills cold starts)
flyctl secrets set MERCHANT_WEBHOOK_SECRET=<long-random-string>   # turn on webhook signature check
```

**Free-tier limits:** 3 shared-cpu-1x 256 MB VMs + 3 GB persistent storage. Way more than enough.

---

## Option 2 — Render.com (easiest, ~3 minutes, free)

Why: connects to GitHub, deploys on push, has a 1-click blueprint.

### Steps

1. Push this repo to GitHub.
2. Go to https://dashboard.render.com → **New** → **Blueprint** → connect your repo.
3. Render reads `render.yaml`, provisions everything, and starts the build.
4. ~3 minutes later you have a URL like `https://auguspay.onrender.com`.

**Free-tier caveat:** the service sleeps after 15 minutes of inactivity. First request after sleep takes ~30 s to wake. For a demo this is fine; for live customer traffic, upgrade to the $7/mo Starter plan (always-on).

---

## Option 3 — Google Cloud Run (most "Google-flavoured" for your resume)

Why: shows you can deploy on GCP. ⚠️ But SQLite + Cloud Run is tricky because Cloud Run is *stateless* — every cold start gives you a fresh empty DB. Two ways to solve:

### Option 3a — Cloud Run + Cloud SQL (Postgres) — production-correct

This requires switching `DATABASE_URL` to Postgres. Steps:

```powershell
# requires gcloud CLI installed and a GCP project
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
gcloud services enable run.googleapis.com sqladmin.googleapis.com artifactregistry.googleapis.com

# 1. create a tiny Postgres
gcloud sql instances create auguspay-db --tier=db-f1-micro --region=asia-south1 --database-version=POSTGRES_15
gcloud sql databases create auguspay --instance=auguspay-db
gcloud sql users set-password postgres --instance=auguspay-db --password=<choose-a-password>

# 2. build & deploy
gcloud run deploy auguspay `
  --source . `
  --region asia-south1 `
  --allow-unauthenticated `
  --add-cloudsql-instances <PROJECT_ID>:asia-south1:auguspay-db `
  --set-env-vars "DATABASE_URL=postgresql+pg8000://postgres:<password>@/auguspay?unix_sock=/cloudsql/<PROJECT_ID>:asia-south1:auguspay-db/.s.PGSQL.5432" `
  --set-env-vars "SECRET_KEY=<long-random-string>"
```

Then add `pg8000>=1.30` (or `psycopg[binary]>=3.1`) to `requirements.txt` and redeploy.

### Option 3b — Cloud Run + min-instances=1 (keeps SQLite alive but data still lost on redeploy)

```powershell
gcloud run deploy auguspay --source . --region asia-south1 --allow-unauthenticated `
  --min-instances 1 --max-instances 1
```

Fine for a quick demo. Don't trust it with real merchant data.

**Cloud Run free tier:** 2 million requests/month, 360,000 GB-seconds memory. Generous.

---

## After deployment — verify it works

Replace `<URL>` with your live URL.

```powershell
# 1. health check
curl <URL>/health
# expected: {"status":"ok"}

# 2. landing redirects to register
curl -i <URL>/
# expected: 307 Temporary Redirect -> /merchant/

# 3. register page renders
curl <URL>/merchant/
# expected: HTML containing "Create shop & start"

# 4. simulate the webhook with a real merchant (do this from the browser after registering)
```

---

## Important things to know before going public

1. **Generate a real `SECRET_KEY`** (32+ random bytes). Default `"dev-change-me"` will leak sessions.
2. **Set `MERCHANT_WEBHOOK_SECRET`** before any real PSP is wired up, or any anonymous POST to `/merchant/api/webhook/upi` can forge settlements.
3. **SQLite is fine for a demo / pilot kirana**, not for >100 merchants. Switch to Postgres for production.
4. **The in-process SSE pub/sub means you must run ONE worker.** For >1 worker, swap to Redis pub/sub (~30 lines of change).
5. **HTTPS is mandatory** for PWAs and service workers. All three platforms above give you that automatically.
6. **Set up an uptime monitor** (BetterStack, UptimeRobot — both free) hitting `/health` every minute.

---

## My recommendation for *this* project right now

If you want it **live in 5 minutes for free**, use **Fly.io**. Persistent SQLite + Mumbai region + SSE-friendly. The `fly.toml` and `Dockerfile` in the repo are already set up — just run the 4 commands in Option 1.

