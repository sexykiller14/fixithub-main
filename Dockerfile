# FixIT Hub
#
# Multi-stage: dependencies are installed into a virtualenv in the builder and
# copied into the runtime image, so the runtime needs no compiler.

FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    FIXITHUB_DATABASE_URL="sqlite:////app/data/fixithub.db"

# A non-root user owns the writable data directory.
RUN groupadd --system fixithub \
    && useradd --system --gid fixithub --home /app fixithub

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY --chown=fixithub:fixithub app/ ./app/
COPY --chown=fixithub:fixithub content/ ./content/
COPY --chown=fixithub:fixithub data/ ./data/
COPY --chown=fixithub:fixithub scripts_download/ ./scripts_download/
COPY --chown=fixithub:fixithub apps_download/ ./apps_download/
COPY --chown=fixithub:fixithub seed.py requirements.txt README.md ./

# data/ holds the SQLite database and the admin password hash, so it is a volume.
# apps_download/ holds admin-uploaded binaries and must be writable, since the
# app writes files there. Neither is stored in git.
RUN mkdir -p /app/data /app/apps_download && chown fixithub:fixithub /app/data /app/apps_download

USER fixithub

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

# One worker, because the rate limiter keeps its counters in the process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
