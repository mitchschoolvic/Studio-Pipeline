import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  WEBSOCKET_PING_INTERVAL,
  WEBSOCKET_RECONNECT_DELAY,
  WEBSOCKET_MAX_EVENTS,
  WEBSOCKET_CONFIG
} from '../constants/websocket';
import { normalizeMessage } from '../utils/messageNormalizer';
import { clearPingInterval, clearReconnectTimeout, cleanupWebSocket } from '../utils/websocketHelpers';

/**
 * Get the WebSocket URL based on current window location
 * This ensures the WebSocket connects to the same server serving the frontend
 */
function getWebSocketUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return `${protocol}//${host}/api/ws`;
}

/**
 * @typedef {Object} WebSocketContextValue
 * @property {boolean} connected - Whether WebSocket is connected
 * @property {Object|null} lastMessage - Last received message
 * @property {Object[]} events - Array of recent events
 * @property {string|null} connectionError - Current connection error message
 * @property {(message: Object) => void} sendMessage - Function to send messages
 * @property {number} reconnectCount - Number of reconnection attempts
 */

const WebSocketContext = createContext(null);

/**
 * WebSocket Provider - Manages a SINGLE shared WebSocket connection
 * 
 * This provider should wrap your entire app (or the portion that needs WebSocket).
 * All components using useWebSocket() will share this single connection.
 * 
 * Benefits:
 * - Single connection instead of multiple per-component connections
 * - Centralized message handling
 * - Consistent state across all consumers
 * - Proper cleanup on unmount
 */
export function WebSocketProvider({ children, url }) {
  const wsUrl = url || getWebSocketUrl();
  const queryClient = useQueryClient();

  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const [events, setEvents] = useState([]);
  const [connectionError, setConnectionError] = useState(null);
  const [reconnectCount, setReconnectCount] = useState(0);
  const [serverTime, setServerTime] = useState(null);  // Server time for debugging

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const pingIntervalRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const isConnectingRef = useRef(false);

  // Track if we just reconnected (for cache refresh)
  const justReconnectedRef = useRef(false);

  const connect = useCallback(() => {
    // Prevent multiple simultaneous connection attempts
    if (isConnectingRef.current) {
      console.log('🔄 Connection already in progress, skipping...');
      return;
    }

    // Cleanup any existing connection
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch (e) {
        // Ignore close errors
      }
      wsRef.current = null;
    }

    isConnectingRef.current = true;

    try {
      console.log(`🔌 Connecting to WebSocket: ${wsUrl}`);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('✅ WebSocket connected');
        isConnectingRef.current = false;
        setConnected(true);
        setConnectionError(null);
        window.wsConnected = true;

        // Check if this is a reconnection (not first connection)
        if (reconnectAttemptsRef.current > 0) {
          justReconnectedRef.current = true;
          console.log('🔄 Reconnected - will refresh stale data');
          
          // Invalidate key queries to refresh potentially stale data
          queryClient.invalidateQueries({ queryKey: ['sessions'] });
          queryClient.invalidateQueries({ queryKey: ['session-files'] });
          queryClient.invalidateQueries({ queryKey: ['worker-status'] });
        }

        // Reset reconnect counter on successful connection
        reconnectAttemptsRef.current = 0;
        setReconnectCount(0);

        // Start ping interval for keepalive
        clearPingInterval(pingIntervalRef);
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, WEBSOCKET_PING_INTERVAL);
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          
          // Skip pong messages from logging
          if (message.type !== 'pong') {
            console.log('📨 WebSocket message:', message.type, message.data?.file_id || '');
          }

          // Normalize message shape using strategy pattern
          const normalized = normalizeMessage(message);

          // Track server time for debugging (don't add to events to avoid spam)
          if (normalized.type === 'server_time') {
            setServerTime(normalized.data?.time || null);
            return;  // Don't add server_time to events or lastMessage
          }

          setLastMessage(normalized);

          // Maintain lightweight global index for large datasets
          if (!window.__sessionIndex) {
            window.__sessionIndex = { files: {}, sessions: {} };
          }

          // Update global index based on message type
          if (normalized.type === 'file_state_change') {
            const d = normalized.data || normalized;
            window.__sessionIndex.files[d.file_id] = {
              ...(window.__sessionIndex.files[d.file_id] || {}),
              state: d.state,
              session_id: d.session_id,
              progress_pct: d.progress_pct,
              progress_stage: d.progress_stage,
              error_message: d.error_message
            };
          } else if (normalized.type === 'session_discovered') {
            const d = normalized.data || normalized;
            window.__sessionIndex.sessions[d.session_id] = {
              id: d.session_id,
              name: d.session_name,
              file_count: d.file_count
            };
          } else if (normalized.type === 'analytics.state') {
            const d = normalized.data || normalized;
            if (window.__sessionIndex.files[d.file_id]) {
              window.__sessionIndex.files[d.file_id].analytics_state = d.state;
              if (d.title) window.__sessionIndex.files[d.file_id].title = d.title;
              if (d.language) window.__sessionIndex.files[d.file_id].language = d.language;
            }
          }

          // Add to events list (ring buffer)
          setEvents((prev) => {
            const newEvents = [normalized, ...prev].slice(0, WEBSOCKET_MAX_EVENTS);
            return newEvents;
          });
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
          setConnectionError('Failed to process server message. Please refresh if issues persist.');
        }
      };

      ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        console.error('WebSocket readyState:', ws.readyState);
        isConnectingRef.current = false;
        setConnectionError('Connection error occurred. Attempting to reconnect...');
      };

      ws.onclose = (event) => {
        console.log('🔌 WebSocket disconnected');
        console.log('Close code:', event.code, 'reason:', event.reason, 'wasClean:', event.wasClean);
        isConnectingRef.current = false;
        setConnected(false);
        window.wsConnected = false;

        // Clear ping interval
        clearPingInterval(pingIntervalRef);

        // Attempt reconnection with exponential backoff (capped)
        if (reconnectAttemptsRef.current < WEBSOCKET_CONFIG.MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current += 1;
          setReconnectCount(reconnectAttemptsRef.current);
          
          const delay = Math.min(
            WEBSOCKET_RECONNECT_DELAY * Math.pow(1.5, reconnectAttemptsRef.current - 1),
            30000 // Max 30 seconds
          );
          
          setConnectionError(`Disconnected from server. Reconnecting in ${Math.round(delay / 1000)}s...`);
          
          clearReconnectTimeout(reconnectTimeoutRef);
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log(`🔄 Attempting reconnect (${reconnectAttemptsRef.current}/${WEBSOCKET_CONFIG.MAX_RECONNECT_ATTEMPTS})...`);
            connect();
          }, delay);
        } else {
          setConnectionError('Connection lost. Please refresh the page to reconnect.');
        }
      };
    } catch (err) {
      console.error('Failed to create WebSocket:', err);
      isConnectingRef.current = false;
      setConnectionError('Failed to establish connection. Please check your network.');
    }
  }, [wsUrl, queryClient]);

  // Connect on mount, cleanup on unmount
  useEffect(() => {
    connect();

    return () => {
      console.log('🧹 WebSocket provider unmounting, cleaning up...');
      cleanupWebSocket(wsRef, reconnectTimeoutRef, pingIntervalRef);
    };
  }, [connect]);

  const sendMessage = useCallback((message) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not connected, cannot send message');
    }
  }, []);

  const value = {
    connected,
    lastMessage,
    events,
    connectionError,
    sendMessage,
    reconnectCount,
    serverTime,
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
}

/**
 * Hook to access the shared WebSocket connection
 * 
 * IMPORTANT: This must be used within a WebSocketProvider
 * 
 * @returns {WebSocketContextValue} WebSocket state and methods
 */
export function useWebSocketContext() {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocketContext must be used within a WebSocketProvider');
  }
  return context;
}

export default WebSocketContext;
