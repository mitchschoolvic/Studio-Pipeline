#!/bin/bash

# Studio Pipeline - Server Shutdown Script (AI MODE)
# This script stops both the backend API and frontend dev server

echo "🛑 Stopping Studio Pipeline Servers (AI MODE)..."

# Kill backend
echo "   Stopping backend (uvicorn)..."
pkill -9 -f "uvicorn main:app" 2>/dev/null && echo "   ✅ Backend stopped" || echo "   ℹ️  Backend not running"

# Kill frontend (target only the process on :5173)
echo "   Stopping frontend (vite on :5173)..."
if lsof -nP -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
	FRONTEND_PID=$(lsof -nP -iTCP:5173 -sTCP:LISTEN -t | head -n1)
	if [ -n "$FRONTEND_PID" ]; then
		kill "$FRONTEND_PID" 2>/dev/null || true
		sleep 1
		kill -9 "$FRONTEND_PID" 2>/dev/null || true
		echo "   ✅ Frontend stopped (PID $FRONTEND_PID)"
	else
		echo "   ℹ️  Could not resolve PID on :5173"
	fi
else
	echo "   ℹ️  Frontend not running on :5173"
fi

sleep 1

echo ""
echo "✅ All servers stopped (AI MODE)!"
echo ""
echo "📝 Logs preserved at:"
echo "  /tmp/backend_ai.log"
echo "  /tmp/vite_server.log"
echo ""
