#!/bin/bash

# Studio Pipeline - Server Startup Script (AI MODE)
# This script starts both the backend API and frontend dev server with AI analytics enabled

set -e  # Exit on error

# Enable AI features
export BUILD_WITH_AI=true

# Use Node 20 from Homebrew
export PATH="/opt/homebrew/opt/node@20/bin:$PATH"

PROJECT_ROOT="/Users/mitch.anderson/Documents/Custom_Apps/Unified-Studio"
VENV_PATH="$PROJECT_ROOT/.venv"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# Helper: print info about any process listening on a port
port_info() {
    local port="$1"
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "   ℹ️  Port $port is in use by:"
        lsof -nP -iTCP:"$port" -sTCP:LISTEN
        local pid
        pid=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t | head -n1)
        if [ -n "$pid" ]; then
            echo "   ℹ️  Process $pid CWD: $(lsof -p "$pid" 2>/dev/null | awk '/ cwd /{print substr($0,index($0,$9))}')"
            echo "   ℹ️  Command: $(ps -o pid,command -p "$pid" | tail -n1)"
        fi
    else
        echo "   ℹ️  Port $port is free."
    fi
}

echo "🚀 Starting Studio Pipeline Servers (AI MODE)..."
echo "   🤖 AI Analytics: ENABLED"
echo ""

# Step 1: Clean up existing processes (targeted)
echo "🧹 Cleaning up existing processes..."

# Backend on :8000
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
    pkill -9 -f "uvicorn main:app" 2>/dev/null || true
fi

# Frontend on :5173 — only kill if it's NOT our project directory
if lsof -nP -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "   Detected existing process on :5173"
    port_info 5173
    EXIST_PID=$(lsof -nP -iTCP:5173 -sTCP:LISTEN -t | head -n1)
    if [ -n "$EXIST_PID" ]; then
        EXIST_CWD=$(lsof -p "$EXIST_PID" 2>/dev/null | awk '/ cwd /{print substr($0,index($0,$9))}')
        if [ "$EXIST_CWD" != "$FRONTEND_DIR" ]; then
            echo "   🚫 Port 5173 in use by another project ($EXIST_CWD). Terminating it so we can start the correct dev server."
            kill "$EXIST_PID" 2>/dev/null || true
            sleep 1
            kill -9 "$EXIST_PID" 2>/dev/null || true
        else
            echo "   ✅ Existing Vite dev server belongs to this project. Reusing it."
            REUSE_FRONTEND=1
        fi
    fi
fi
sleep 1

# Step 2: Start Backend with AI enabled
echo "🔧 Starting Backend API Server (AI MODE)..."
cd "$BACKEND_DIR"
BUILD_WITH_AI=true nohup "$VENV_PATH/bin/python" -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info > /tmp/backend_ai.log 2>&1 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"
echo "   Logs: /tmp/backend_ai.log"

# Wait for backend to start
echo "   Waiting for backend to be ready..."
for i in {1..10}; do
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "   ✅ Backend is ready!"
        break
    fi
    sleep 1
done

# Verify AI features are enabled
echo "   Checking AI analytics status..."
if curl -s http://localhost:8000/api/analytics/stats > /dev/null 2>&1; then
    echo "   ✅ AI analytics endpoints are available!"
else
    echo "   ⚠️  Warning: AI analytics endpoints not responding"
fi

# Step 3: Start Frontend
echo ""
echo "🎨 Starting/Verifying Frontend Dev Server..."
cd "$FRONTEND_DIR"
if [ -z "$REUSE_FRONTEND" ]; then
    VITE_APP_DEV_MODE="true" VITE_APP_AI_ENABLED="true" nohup ./node_modules/.bin/vite --host 0.0.0.0 --port 5173 > /tmp/vite_server.log 2>&1 &
    FRONTEND_PID=$!
    echo "   Frontend PID: $FRONTEND_PID"
    echo "   Logs: /tmp/vite_server.log"
else
    FRONTEND_PID=$(lsof -nP -iTCP:5173 -sTCP:LISTEN -t | head -n1)
    echo "   Reusing existing Frontend PID: $FRONTEND_PID"
    echo "   Logs: /tmp/vite_server.log (if applicable)"
fi

# Wait for frontend to start
echo "   Waiting for frontend to be ready..."
for i in {1..20}; do
        if lsof -nP -iTCP:5173 -sTCP:LISTEN > /dev/null 2>&1; then
                echo "   ✅ Frontend port is listening"
                break
        fi
        sleep 1
done

# Verify that the served source belongs to THIS repo by checking the absolute path in Vite's dev transform
VERIFY_PATH="$FRONTEND_DIR/src/main.jsx"
if curl -s "http://localhost:5173/src/main.jsx" | grep -Fq "$VERIFY_PATH"; then
    echo "   ✅ Verified served source matches this workspace ($VERIFY_PATH)"
else
    echo "   ❌ Frontend at :5173 is not serving this workspace. Details:"
    port_info 5173
    echo "   Aborting to avoid using the wrong dev server."
    exit 1
fi

# Step 4: Summary
echo ""
echo "✅ All servers started successfully (AI MODE)!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Backend API:  http://localhost:8000"
echo "  Frontend UI:  http://localhost:5173"
echo "  AI Analytics: http://localhost:8000/api/analytics/stats"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🤖 AI Features:"
echo "  • Transcription (Whisper)"
echo "  • Content Analysis (LLM)"
echo "  • Scheduled Processing"
echo "  • Excel Export"
echo ""
echo "📊 Process IDs:"
echo "  Backend:  $BACKEND_PID"
echo "  Frontend: $FRONTEND_PID"
echo ""
echo "📝 View Logs:"
echo "  tail -f /tmp/backend_ai.log"
echo "  tail -f /tmp/vite_server.log"
echo ""
echo "🛑 Stop Servers:"
echo "  ./stop_servers_ai.sh"
echo ""

# Open browser (optional - set SKIP_OPEN=1 to disable)
if [ "$SKIP_OPEN" != "1" ]; then
    echo "🌐 Opening browser..."
    sleep 2
    open http://localhost:5173/
fi

echo "✨ Ready to use with AI analytics!"
