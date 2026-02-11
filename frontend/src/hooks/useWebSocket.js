import { useContext } from 'react';
import WebSocketContext from '../contexts/WebSocketContext';

/**
 * @typedef {Object} WebSocketMessage
 * @property {string} type - Message type
 * @property {*} [payload] - Message payload
 * @property {string} [timestamp] - Message timestamp
 */

/**
 * @typedef {Object} WebSocketHookReturn
 * @property {boolean} connected - Whether WebSocket is connected
 * @property {WebSocketMessage|null} lastMessage - Last received message
 * @property {WebSocketMessage[]} events - Array of recent events
 * @property {string|null} connectionError - Current connection error message
 * @property {(message: Object) => void} sendMessage - Function to send messages
 */

/**
 * Custom React hook for WebSocket connection to Studio Pipeline
 *
 * This hook now uses a SHARED WebSocket connection via WebSocketContext.
 * All components calling useWebSocket() share the same underlying connection.
 *
 * Features:
 * - Single shared connection (via WebSocketProvider)
 * - Automatic connection management
 * - Reconnection on disconnect with cache invalidation
 * - Event message handling
 * - Ping/pong keepalive
 * - User-facing error feedback
 *
 * @returns {WebSocketHookReturn} WebSocket state and methods
 */
export function useWebSocket() {
  const context = useContext(WebSocketContext);
  
  if (!context) {
    // Provide helpful error message
    throw new Error(
      'useWebSocket must be used within a WebSocketProvider. ' +
      'Wrap your app with <WebSocketProvider> in App.jsx'
    );
  }

  return context;
}
