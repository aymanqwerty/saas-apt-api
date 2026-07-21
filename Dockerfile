# syntax=docker/dockerfile:1

# --- Base image -------------------------------------------------------------
FROM python:3.12-slim AS base

# Keep Python lean and predictable inside containers.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps: build tools are only needed if a wheel is missing; psycopg[binary]
# ships wheels so we keep this minimal. curl is handy for healthchecks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# --- Python dependencies (cached layer) -------------------------------------
COPY requirements.txt ./
RUN pip install -r requirements.txt

# --- Application code --------------------------------------------------------
COPY . .

# Ensure the entrypoint is executable regardless of the host's file mode
# (Windows checkouts drop the exec bit).
RUN chmod +x docker-entrypoint.sh

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/media \
    && chown -R appuser:appuser /app
USER appuser

# Cloud Run (and most PaaS) inject $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Entrypoint runs DB migrations, then starts the server.
ENTRYPOINT ["./docker-entrypoint.sh"]
