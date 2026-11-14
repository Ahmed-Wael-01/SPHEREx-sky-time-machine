
#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo ""
    echo "Stopping servers..."

    [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
    [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true

    wait 2>/dev/null || true
    echo "All servers stopped."
}

trap cleanup EXIT INT TERM

cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
    echo "ERROR: .venv not found in repository root."
    exit 1
fi

if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: Node.js is not installed."
    exit 1
fi

echo "Checking dependencies..."

source .venv/bin/activate

if [[ ! -d "frontend/node_modules" ]]; then
    echo "Installing frontend dependencies..."
    (cd frontend && npm install)
fi

echo ""
echo "Starting Flask API..."

(
    cd backend
    python app.py
) &
BACKEND_PID=$!

echo "Starting React frontend..."

(
    cd frontend
    npm run dev -- --host 0.0.0.0
) &
FRONTEND_PID=$!

echo ""
echo "===================================="
echo " SPHEREx Sky Time Machine"
echo "===================================="
echo "Frontend: http://localhost:5173/"
echo "API:      http://localhost:5000/"
echo ""
echo "Try RW Aur:"
echo "http://localhost:5173/?target=rw-aur"
echo ""
echo "Try Difference Mode:"
echo "http://localhost:5173/?ra=76.956&dec=30.401&fov=0.2&mode=diff"
echo ""
echo "Press Ctrl+C to stop both servers."
echo "===================================="

wait
