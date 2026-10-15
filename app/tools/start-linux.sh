#!/usr/bin/env bash
# Native Linux application and router share the host loopback network.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then
  # Trusted, private shell-compatible deployment config; never echo its contents.
  set -a
  source .env
  set +a
fi
PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" || ! -f frontend/dist/index.html || ! -f sample_data/catalog.json ]]; then
  printf '%s\n' 'Missing Linux venv, frontend build or private sample catalog. Follow DEPLOYMENT.md.' >&2
  exit 2
fi
: "${AICADEMIYA_DATA_DIR:?Set AICADEMIYA_DATA_DIR to a fresh private production directory}"
export AICADEMIYA_DEMO_ENABLED="${AICADEMIYA_DEMO_ENABLED:-false}"
export AICADEMIYA_WEB_SEARCH_ENABLED="${AICADEMIYA_WEB_SEARCH_ENABLED:-false}"
# One application process: startup recovery of pending requests is not multi-worker safe.
exec "$PYTHON" -m uvicorn backend.aicademiya.main:app \
  --host "${AICADEMIYA_HOST:-127.0.0.1}" --port "${AICADEMIYA_PORT:-18773}" \
  --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
