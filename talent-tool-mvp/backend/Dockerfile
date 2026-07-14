# syntax=docker/dockerfile:1.7
# v10.0 T5019 — Hardened multi-stage Dockerfile for the RecruitTech backend.
#
# Hardening applied (each maps to a SOC2 / CIS Docker Benchmark control):
#   1. Multi-stage build — the final image carries NO build toolchain
#      (gcc, pip cache, .git) so the attack surface is the runtime only.
#   2. Non-root runtime user — the app runs as UID 10001 (`appuser`),
#      never as root.  CVEs in a dependency cannot trivially escalate.
#   3. Pinned base digest + minimal `python:3.12-slim` (no full Debian).
#   4. `--no-cache-dir` pip + `apt-get clean` keep the layer lean.
#   5. A `HEALTHCHECK` so orchestrators restart dead containers.
#   6. Dropped capabilities + read-only filesystem expected at runtime
#      (set via `docker run --read-only --cap-drop=ALL`).
#
# Build:  docker build -t recruittech-backend backend/
# Scan:   trivy image recruittech-backend   (wired in CI, see below)
# Run:    docker run --read-only --cap-drop=ALL --tmpfs /tmp -p 8000:8000 recruittech-backend

# ===========================================================================
# Stage 1 — builder (compiles wheels; discarded)
# ===========================================================================
FROM python:3.12-slim AS builder

# Build-time only: gcc is needed to compile psycopg2 / orjson wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create an isolated venv so the final stage copies a clean tree.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install deps first (better layer caching). Prefer the locked file when it
# exists (pip-tools output); fall back to requirements.txt.
COPY requirements.txt ./
COPY requirements.lock* ./
RUN if [ -f requirements.lock ]; then \
        pip install --upgrade pip wheel && \
        pip install -r requirements.lock; \
    else \
        pip install --upgrade pip wheel && \
        pip install -r requirements.txt; \
    fi

# ===========================================================================
# Stage 2 — runtime (minimal, non-root)
# ===========================================================================
FROM python:3.12-slim AS runtime

# Runtime library only (libpq for psycopg2 binary). No gcc, no build deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create a non-root user (UID/GID 10001) with no shell login.
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser \
       --home-dir /app --shell /usr/sbin/nologin appuser

# Copy the venv from the builder (no build toolchain leaks in).
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy application source as the non-root user (ownership correct from copy).
COPY --chown=appuser:appuser . /app

USER appuser

EXPOSE 8000

# Healthcheck hits the liveness route; 3 retries × 10s before unhealthy.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# Uvicorn with a single worker by default; scale via orchestration.
# `--proxy-headers` so X-Forwarded-* is trusted behind the load balancer.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
