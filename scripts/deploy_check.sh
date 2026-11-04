#!/usr/bin/env bash
# ==============================================================================
# Production Deployment Preflight Health Check
# Validates database connectivity, schema migrations, environment, and storage.
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "==> Running Issue-to-PR Production Preflight..."

export PYTHONPATH="${ROOT_DIR}/backend:${PYTHONPATH}"

if [ -f "${ROOT_DIR}/backend/.venv/bin/python" ]; then
    PYTHON_BIN="${ROOT_DIR}/backend/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    echo "ERROR: python3 not found."
    exit 1
fi

"${PYTHON_BIN}" "${ROOT_DIR}/backend/app/core/preflight.py"

echo "==> Preflight check completed successfully!"
