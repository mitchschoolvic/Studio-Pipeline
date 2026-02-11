import { useEffect, useCallback } from 'react';
import { useWebSocketConnection } from './useWebSocketConnection';
import { useWebSocketReconnect } from './useWebSocketReconnect';
import { useWebSocketKeepalive } from './useWebSocketKeepalive';
import { useWebSocketMessages } from './useWebSocketMessages';

/**
 * Get the WebSocket URL based on current window location
 * This ensures the WebSocket connects to the same server serving the frontend
 */
function getWebSocketUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host; // includes port if present
  return `${protocol}//${host}/api/ws`;
}

/**
 * @typedef {Object} WebSocketHookReturn
 * @property {boolean} connected - Whether WebSocket is connected
 * @property {Object|null} lastMessage - Last received message
 * @property {Array} events - Array of recent events
 * @property {string|null} connectionError - Current connection error message
 * @property {string|null} messageError - Message processing error
 * @property {(message: Object) => void} sendMessage - Function to send messages
 */

/**
 * Composed WebSocket hook using smaller, focused hooks
 *
 * This is a refactored version that composes multiple smaller hooks,
 * following Single Responsibility Principle. Each sub-hook handles one concern:
 * - Connection lifecycle
 * - Reconnection logic
 * - Message handling
 * - Keepalive (ping/pong)
 *
 * @param {string} [url] - WebSocket URL (defaults to current location)
 * @returns {WebSocketHookReturn} WebSocket state and methods
 */
export function useWebSocketComposed(url) {
  // Use dynamic URL if not provided
  const wsUrl = url || getWebSocketUrl();
  
  // Initialize message handling first (needs ws reference)
  const {
    lastMessage,
    events,
    handleMessage,
    sendMessage: sendMessageInternal,
    messageError,
  } = useWebSocketMessages(null); // Will be updated with ws instance

  // Initialize keepalive
  const sendPing = useCallback(() => {
    sendMessageInternal({ type: 'ping' });
  }, [sendMessageInternal]);

  const { startKeepalive, stopKeepalive } = useWebSocketKeepalive(sendPing);

  // Connection handlers
  const handleOpen = useCallback(() => {
    startKeepalive();
    cancelReconnect(); // Reset reconnection counter on successful connect
  }, [startKeepalive]);

  const handleClose = useCallback(() => {
    stopKeepalive();
    scheduleReconnect();
  }, [stopKeepalive]);

  const handleError = useCallback(() => {
    // Error handling is done in connection hook
  }, []);

  // Initialize connection
  const {
    connected,
    ws,
    connect,
    disconnect,
    connectionError,
  } = useWebSocketConnection(wsUrl, handleOpen, handleMessage, handleError, handleClose);

  // Initialize reconnection (after connection to use connect function)
  const { scheduleReconnect, cancelReconnect } = useWebSocketReconnect(connect);

  // Update message handler with ws instance
  const sendMessage = useCallback((message) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not connected');
    }
  }, [ws]);

  // Initial connection on mount
  useEffect(() => {
    connect();

    // Cleanup on unmount
    return () => {
      stopKeepalive();
      cancelReconnect();
      disconnect();
    };
  }, [connect, disconnect, stopKeepalive, cancelReconnect]);

  return {
    connected,
    lastMessage,
    events,
    connectionError,
    messageError,
    sendMessage,
  };
}
