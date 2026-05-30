# Auguspay Merchant Toolkit -- production container.
#
# Build:   docker build -t auguspay .
# Run:     docker run -p 8080:8080 -e SECRET_KEY=$(openssl rand -hex 32) auguspay
#
# Works on: Google Cloud Run, Fly.io, Render, Railway, AWS App Runner,
#           Azure Container Apps, Kubernetes, Docker Compose, plain VM.

FROM python:3.12-slim AS base

# faster, leaner Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# install deps first (better layer caching)
COPY requirements.txt .
RUN pip install -r requirements.txt

# copy source
COPY app.py merchant_toolkit.py ./
COPY templates ./templates
COPY static ./static

# persistent SQLite goes here. Mount a volume to /data in prod.
RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/auguspay.db

# Cloud Run / Fly / Render all inject $PORT; default 8080 for local
ENV PORT=8080
EXPOSE 8080

# don't run as root
RUN useradd -r -u 1000 -m app && chown -R app:app /app /data
USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; \
                 sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{__import__(\"os\").environ.get(\"PORT\",\"8080\")}/health').status==200 else 1)"

# uvicorn with one worker; SSE pub/sub is in-process so multi-worker needs Redis.
# For >1 worker, add Redis pub/sub or switch to a single-worker autoscaled deploy.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]

