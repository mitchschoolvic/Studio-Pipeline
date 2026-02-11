#!/bin/bash
# ==============================================================================
# Studio Pipeline - Stop Backend Helper
# ==============================================================================
# Helper script to stop the backend server
# ==============================================================================

LOG_DIR="${HOME}/Library/Logs/StudioPipeline"
PID_FILE="${LOG_DIR}/backend.pid"

if [ ! -f "${PID_FILE}" ]; then
    echo "Backend is not running (PID file not found)"
    exit 0
fi

BACKEND_PID=$(cat "${PID_FILE}")

if ! kill -0 ${BACKEND_PID} 2>/dev/null; then
    echo "Backend is not running (PID ${BACKEND_PID} not found)"
    rm -f "${PID_FILE}"
    exit 0
fi

echo "Stopping Studio Pipeline backend (PID ${BACKEND_PID})..."
kill ${BACKEND_PID}

# Wait for graceful shutdown
wait_count=0
while kill -0 ${BACKEND_PID} 2>/dev/null && [ $wait_count -lt 10 ]; do
    sleep 0.5
    wait_count=$((wait_count + 1))
    echo -n "."
done
echo ""

# Force kill if still running
if kill -0 ${BACKEND_PID} 2>/dev/null; then
    echo "Force stopping backend..."
    kill -9 ${BACKEND_PID} 2>/dev/null || true
fi

rm -f "${PID_FILE}"
echo "✓ Backend stopped successfully"
