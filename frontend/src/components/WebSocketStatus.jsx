/**
 * WebSocketStatus - Connection status indicator with server time
 * 
 * Shows:
 * - Connection status (green dot = connected, red = disconnected)
 * - Server time (HH:MM:SS) pushed from backend for debugging
 * 
 * Use this to diagnose if:
 * - Frontend is listening (shows connected)
 * - Backend is pushing (time updates every second)
 */

import { useWebSocket } from '../hooks/useWebSocket';
import './WebSocketStatus.css';

export function WebSocketStatus() {
  const { connected, serverTime, reconnectCount } = useWebSocket();

  return (
    <div className="ws-status">
      <div className={`ws-status-dot ${connected ? 'connected' : 'disconnected'}`} />
      <span className="ws-status-label">
        {connected ? 'WS Connected' : `WS Disconnected${reconnectCount > 0 ? ` (retry ${reconnectCount})` : ''}`}
      </span>
      {serverTime && (
        <span className="ws-status-time">
          Server: {serverTime}
        </span>
      )}
    </div>
  );
}
