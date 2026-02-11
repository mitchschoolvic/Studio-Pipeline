/**
 * WebSocket configuration constants
 *
 * Centralized configuration to avoid magic numbers and improve maintainability.
 * These values should match the backend WebSocketConfig class.
 */

export const WEBSOCKET_CONFIG = {
  PING_INTERVAL: 30000,           // Ping every 30 seconds
  RECONNECT_DELAY: 3000,          // Reconnect after 3 seconds
  MAX_EVENTS: 100,                // Maximum events to keep in history
  CONNECTION_TIMEOUT: 60000,      // 1 minute connection timeout
  MAX_RECONNECT_ATTEMPTS: 5,      // Maximum reconnection attempts before giving up
};

// Legacy exports for backward compatibility (deprecated - use WEBSOCKET_CONFIG instead)
export const WEBSOCKET_PING_INTERVAL = WEBSOCKET_CONFIG.PING_INTERVAL;
export const WEBSOCKET_RECONNECT_DELAY = WEBSOCKET_CONFIG.RECONNECT_DELAY;
export const WEBSOCKET_MAX_EVENTS = WEBSOCKET_CONFIG.MAX_EVENTS;
