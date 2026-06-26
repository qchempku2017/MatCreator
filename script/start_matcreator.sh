#!/usr/bin/env bash
set -euo pipefail

PROJ_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MATCREATOR_HOME="${MATCREATOR_HOME:-$HOME/.matcreator}"
MATCREATOR_HOME="${MATCREATOR_HOME/#\~/$HOME}"
LOG_DIR="${MATCREATOR_LOG_DIR:-$MATCREATOR_HOME/logs}"
LOG_DIR="${LOG_DIR/#\~/$HOME}"
mkdir -p "$LOG_DIR"

# Configurable host/port variables
MATCREATOR_ADK_HOST="${MATCREATOR_ADK_HOST:-127.0.0.1}"
MATCREATOR_ADK_PORT="${MATCREATOR_ADK_PORT:-8000}"
MATCREATOR_WEB_HOST="${MATCREATOR_WEB_HOST:-127.0.0.1}"
MATCREATOR_WEB_PORT="${MATCREATOR_WEB_PORT:-8001}"
MATCREATOR_FRONTEND_HOST="${MATCREATOR_FRONTEND_HOST:-127.0.0.1}"
MATCREATOR_FRONTEND_PORT="${MATCREATOR_FRONTEND_PORT:-5173}"

# Export env vars for child processes
export MATCREATOR_ADK_PORT
export ADK_LOCAL_PORT="$MATCREATOR_ADK_PORT"
export MATCREATOR_WEB_PORT
export MATCREATOR_FRONTEND_PORT

cleanup() {
    echo ""
    echo "Shutting down services..."
    [[ -n "${PID_API:-}" ]] && kill "$PID_API" 2>/dev/null || true
    [[ -n "${PID_WEB:-}" ]] && kill "$PID_WEB" 2>/dev/null || true
    [[ -n "${PID_VITE:-}" ]] && kill "$PID_VITE" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "All services stopped."
}
trap cleanup SIGINT SIGTERM

cd "$PROJ_ROOT"

echo "Starting ADK API server (port $MATCREATOR_ADK_PORT)..."
MATCREATOR_API_LOG_LEVEL="${MATCREATOR_API_LOG_LEVEL:-info}"
matcreator api-server --host "$MATCREATOR_ADK_HOST" --port "$MATCREATOR_ADK_PORT" --log-level "$MATCREATOR_API_LOG_LEVEL" >"$LOG_DIR/api-server.log" 2>&1 &
PID_API=$!
sleep 1

echo "Starting FastAPI middle layer (port $MATCREATOR_WEB_PORT)..."
python web/main.py >"$LOG_DIR/web-main.log" 2>&1 &
PID_WEB=$!
sleep 1

echo "Starting Vite frontend (port $MATCREATOR_FRONTEND_PORT)..."
cd "$PROJ_ROOT/web/vite-frontend"
npm run dev >"$LOG_DIR/vite.log" 2>&1 &
PID_VITE=$!

echo ""
echo "All services running:"
echo "  ADK API server : http://$MATCREATOR_ADK_HOST:$MATCREATOR_ADK_PORT"
echo "  FastAPI layer  : http://$MATCREATOR_WEB_HOST:$MATCREATOR_WEB_PORT"
echo "  Frontend       : http://$MATCREATOR_FRONTEND_HOST:$MATCREATOR_FRONTEND_PORT"
echo ""
echo "Logs: $LOG_DIR/{api-server,web-main,vite}.log"
echo "Press Ctrl+C to stop all services."

wait
