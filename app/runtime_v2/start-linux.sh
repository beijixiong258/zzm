#!/usr/bin/env bash
# AIcademiya_V2: one worker, external persistent data, optional trusted config.
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
# systemd supplies EnvironmentFile; for a manual start set AICADEMIYA_CONFIG.
if [[ -n "${AICADEMIYA_CONFIG:-}" ]]; then
  set -a
  source "$AICADEMIYA_CONFIG"
  set +a
fi
PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" || ! -f frontend/dist/index.html || ! -f sample_data/catalog.json ]]; then
  printf '%s\n' 'Missing Linux venv, frontend build or private seed. Follow RUNTIME_V2.md.' >&2
  exit 2
fi
: "${AICADEMIYA_DATA_DIR:?Set the persistent absolute data directory}"
if [[ "$AICADEMIYA_DATA_DIR" != /* ]]; then
  printf '%s\n' 'Data must be absolute and outside the release tree.' >&2
  exit 2
fi
DATA_ROOT="$(realpath -m -- "$AICADEMIYA_DATA_DIR")"
if [[ "$DATA_ROOT" == "$ROOT" || "$DATA_ROOT" == "$ROOT/"* ]]; then
  printf '%s\n' 'Data must be absolute and outside the release tree.' >&2
  exit 2
fi
export AICADEMIYA_DEMO_ENABLED="${AICADEMIYA_DEMO_ENABLED:-false}"
export AICADEMIYA_WEB_SEARCH_ENABLED="${AICADEMIYA_WEB_SEARCH_ENABLED:-false}"
exec "$PYTHON" -m uvicorn backend.aicademiya.main:app \
  --host "${AICADEMIYA_HOST:-127.0.0.1}" --port "${AICADEMIYA_PORT:-18773}" \
  --workers 1 --proxy-headers --forwarded-allow-ips "${AICADEMIYA_FORWARDED_ALLOW_IPS:-127.0.0.1}"
