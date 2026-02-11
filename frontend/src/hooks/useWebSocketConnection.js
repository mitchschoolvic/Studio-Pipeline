import { useState, useEffect, useCallback, useRef } from 'react';
import { WEBSOCKET_CONFIG } from '../constants/websocket';

/**
 * @typedef {Object} WebSocketConnectionReturn
 * @property {boolean} connected - Whether WebSocket is connected
 * @property {WebSocket|null} ws - WebSocket instance
 * @property {() => void} connect - Function to initiate connection
 * @property {() => void} disconnect - Function to close connection
 * @property {string|null} connectionError - Current connection error message
 */

/**
 * Hook for managing WebSocket connection lifecycle
 *
 * Handles connection establishment, state tracking, and disconnection.
 * This is a focused hook following Single Responsibility Principle.
 *
 * @param {string} url - WebSocket URL
 * @param {Function} onOpen - Callback when connection opens
 * @param {Function} onMessage - Callback when message received
 * @param {Function} onError - Callback when error occurs
 * @param {Function} onClose - Callback when connection closes
 * @returns {WebSocketConnectionReturn} Connection state and methods
 */
export function useWebSocketConnection(url, onOpen, onMessage, onError, onClose) {
  const [connected, setConnected] = useState(false);
  const [connectionError, setConnectionError] = useState(null);
  const wsRef = useRef(null);

  const connect = useCallback(() => {
    try {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        console.log('WebSocket already connected');
        return;
      }

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('✅ WebSocket connected');
        setConnected(true);
        setConnectionError(null);
        onOpen?.();
      };

      ws.onmessage = (event) => {
        onMessage?.(event);
      };

      ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        setConnectionError('Connection error occurred. Attempting to reconnect...');
        onError?.(error);
      };

      ws.onclose = () => {
        console.log('🔌 WebSocket disconnected');
        setConnected(false);
        setConnectionError('Disconnected from server. Reconnecting...');
        onClose?.();
      };
    } catch (err) {
      console.error('Failed to create WebSocket:', err);
      setConnectionError('Failed to establish connection. Please check your network.');
    }
  }, [url, onOpen, onMessage, onError, onClose]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  return {
    connected,
    ws: wsRef.current,
    connect,
    disconnect,
    connectionError,
  };
}
