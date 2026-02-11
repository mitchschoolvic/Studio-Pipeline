#!/bin/bash
# ==============================================================================
# Studio Pipeline - App Launcher Script
# ==============================================================================
# This script is embedded in the macOS .app bundle and handles:
# 1. Starting the FastAPI backend server
# 2. Waiting for the server to be ready
# 3. Opening the frontend in the default browser
# 4. Graceful shutdown on app quit
# ==============================================================================

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ROOT="${SCRIPT_DIR}/.."
BACKEND_DIR="${SCRIPT_DIR}/backend"
BACKEND_EXEC="${BACKEND_DIR}/backend"

# Log file location
LOG_DIR="${HOME}/Library/Logs/StudioPipeline"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/app.log"

# Server configuration
HOST="127.0.0.1"
PORT="8000"
HEALTH_URL="http://${HOST}:${PORT}/api/health"
FRONTEND_URL="http://${HOST}:${PORT}/"  # Backend serves frontend at root

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ==============================================================================
# Helper Functions
# ==============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" | tee -a "${LOG_FILE}"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "${LOG_FILE}"
}

log_info() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "${LOG_FILE}"
}

# Check if backend server is already running
check_existing_server() {
    if lsof -Pi :${PORT} -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_info "Port ${PORT} is already in use"

        # Check if it's our backend
        if curl -s "${HEALTH_URL}" >/dev/null 2>&1; then
            log_info "Studio Pipeline is already running"
            open_browser
            exit 0
        else
            log_error "Port ${PORT} is in use by another application"
            log_error "Please stop the other application and try again"

            # Show error dialog
            osascript -e 'display dialog "Studio Pipeline cannot start because port '"${PORT}"' is already in use by another application.\n\nPlease stop the other application and try again." buttons {"OK"} default button "OK" with icon stop with title "Studio Pipeline"'
            exit 1
        fi
    fi
}

# Start the backend server
start_backend() {
    log "Starting Studio Pipeline backend..."

    # Set environment variables
    export PYTHONUNBUFFERED=1
    export PYTHONDONTWRITEBYTECODE=1

    # Set resource paths for the bundled app
    export STUDIO_PIPELINE_RESOURCES="${BACKEND_DIR}"
    export STUDIO_PIPELINE_SWIFT_TOOLS="${BACKEND_DIR}/swift_tools"
    export STUDIO_PIPELINE_MODELS="${BACKEND_DIR}/models"

    # Start backend as background process
    cd "${BACKEND_DIR}"
    "${BACKEND_EXEC}" >> "${LOG_FILE}" 2>&1 &
    BACKEND_PID=$!

    log "Backend started with PID ${BACKEND_PID}"
    echo "${BACKEND_PID}" > "${LOG_DIR}/backend.pid"
}

# Wait for backend to be ready
wait_for_backend() {
    log "Waiting for backend to be ready..."

    local max_retries=30
    local retry_interval=1
    local retries=0

    while [ $retries -lt $max_retries ]; do
        if curl -s -f "${HEALTH_URL}" >/dev/null 2>&1; then
            log_success "Backend is ready!"
            return 0
        fi

        # Check if backend process is still running
        if ! kill -0 ${BACKEND_PID} 2>/dev/null; then
            log_error "Backend process died unexpectedly"
            log_error "Check logs at: ${LOG_FILE}"

            # Show error dialog
            osascript -e 'display dialog "Studio Pipeline failed to start.\n\nCheck logs at:\n'"${LOG_FILE}"'" buttons {"Open Logs", "OK"} default button "OK" with icon stop with title "Studio Pipeline"' | grep "Open Logs" && open "${LOG_DIR}"
            exit 1
        fi

        retries=$((retries + 1))
        sleep ${retry_interval}
    done

    log_error "Backend failed to start within ${max_retries} seconds"
    log_error "Check logs at: ${LOG_FILE}"

    # Kill the backend process
    kill ${BACKEND_PID} 2>/dev/null || true

    # Show error dialog
    osascript -e 'display dialog "Studio Pipeline backend failed to start within '"${max_retries}"' seconds.\n\nCheck logs at:\n'"${LOG_FILE}"'" buttons {"Open Logs", "OK"} default button "OK" with icon stop with title "Studio Pipeline"' | grep "Open Logs" && open "${LOG_DIR}"
    exit 1
}

# Open browser to frontend
open_browser() {
    log "Opening Studio Pipeline in browser..."
    open "${FRONTEND_URL}"
    log_success "Studio Pipeline is now running at ${FRONTEND_URL}"
}

# Cleanup on exit (only called on error)
cleanup() {
    log "Shutting down Studio Pipeline (error condition)..."

    # Read PID from file
    if [ -f "${LOG_DIR}/backend.pid" ]; then
        BACKEND_PID=$(cat "${LOG_DIR}/backend.pid")

        if kill -0 ${BACKEND_PID} 2>/dev/null; then
            log "Stopping backend (PID ${BACKEND_PID})..."
            kill ${BACKEND_PID}

            # Wait for graceful shutdown
            local wait_count=0
            while kill -0 ${BACKEND_PID} 2>/dev/null && [ $wait_count -lt 10 ]; do
                sleep 0.5
                wait_count=$((wait_count + 1))
            done

            # Force kill if still running
            if kill -0 ${BACKEND_PID} 2>/dev/null; then
                log "Force stopping backend..."
                kill -9 ${BACKEND_PID} 2>/dev/null || true
            fi

            log_success "Backend stopped"
        fi

        rm -f "${LOG_DIR}/backend.pid"
    fi

    log "Studio Pipeline shutdown complete"
    exit 1
}

# ==============================================================================
# Main Entry Point
# ==============================================================================

main() {
    log "============================================"
    log "Studio Pipeline - Starting..."
    log "============================================"
    log "Script Dir: ${SCRIPT_DIR}"
    log "Backend Dir: ${BACKEND_DIR}"
    log "Backend Exec: ${BACKEND_EXEC}"
    log "Log File: ${LOG_FILE}"
    log "============================================"

    # Trap signals for cleanup
    trap cleanup INT TERM EXIT

    # Verify backend executable exists
    if [ ! -f "${BACKEND_EXEC}" ]; then
        log_error "Backend executable not found at: ${BACKEND_EXEC}"
        osascript -e 'display dialog "Studio Pipeline is corrupted.\n\nBackend executable not found.\n\nPlease reinstall the application." buttons {"OK"} default button "OK" with icon stop with title "Studio Pipeline"'
        exit 1
    fi

    # Check for existing server
    check_existing_server

    # Start backend
    start_backend

    # Wait for backend to be ready
    wait_for_backend

    # Open browser
    open_browser

    # Log success
    log_success "Studio Pipeline started successfully"
    log "Backend running with PID ${BACKEND_PID}"
    log "Logs are being written to: ${LOG_FILE}"
    log "App will remain in dock - quit from dock or Activity Monitor to stop"

    # Keep the app alive by monitoring the backend process
    # This keeps the dock icon visible
    while kill -0 ${BACKEND_PID} 2>/dev/null; do
        sleep 2
    done

    # Backend has stopped
    log "Backend process ended"
    rm -f "${LOG_DIR}/backend.pid"

    # Remove cleanup trap and exit normally
    trap - EXIT
    exit 0
}

# Run main
main "$@"
