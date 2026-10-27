#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

echo "=========================================================="
echo " Starting Issue-to-PR Platform for Google Antigravity"
echo "=========================================================="

# Ensure PostgreSQL service is started
if command -v brew >/dev/null 2>&1; then
  echo "Checking PostgreSQL service..."
  brew services start postgresql@16 >/dev/null 2>&1 || true
fi

# Ensure database exists
echo "Verifying PostgreSQL database 'issuetopr'..."
psql -U $(whoami) -d postgres -c "CREATE DATABASE issuetopr;" 2>/dev/null || true

# Start Backend API
echo "Starting FastAPI Backend on http://127.0.0.1:8000 ..."
cd "$DIR/backend"
PYTHONPATH=. "$DIR/backend/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# Start Frontend Dev Server
echo "Starting React Frontend on http://127.0.0.1:5173 ..."
cd "$DIR/frontend"
npm run dev -- --host 127.0.0.1 --port 5173 &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "Shutting down Issue-to-PR Platform..."
  kill $BACKEND_PID 2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  exit 0
}

trap cleanup INT TERM

echo ""
echo "=========================================================="
echo " Issue-to-PR Platform is ready!"
echo " Web Dashboard:  http://127.0.0.1:5173"
echo " API Docs:       http://127.0.0.1:8000/docs"
echo " Antigravity App: Connected"
echo " Press Ctrl+C to terminate services"
echo "=========================================================="
echo ""

wait
