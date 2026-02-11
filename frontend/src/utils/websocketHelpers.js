/**
 * WebSocket Helper Functions
 *
 * Extracted cleanup and utility functions to eliminate code duplication
 * and improve maintainability of WebSocket connection management.
 */

/**
 * Clear a ping interval reference safely
 *
 * @param {Object} pingIntervalRef - React ref containing interval ID
 */
export function clearPingInterval(pingIntervalRef) {
  if (pingIntervalRef.current) {
    clearInterval(pingIntervalRef.current);
    pingIntervalRef.current = null;
  }
}

/**
 * Clear a reconnect timeout reference safely
 *
 * @param {Object} reconnectTimeoutRef - React ref containing timeout ID
 */
export function clearReconnectTimeout(reconnectTimeoutRef) {
  if (reconnectTimeoutRef.current) {
    clearTimeout(reconnectTimeoutRef.current);
    reconnectTimeoutRef.current = null;
  }
}

/**
 * Close a WebSocket connection safely
 *
 * @param {Object} wsRef - React ref containing WebSocket instance
 */
export function closeWebSocket(wsRef) {
  if (wsRef.current) {
    wsRef.current.close();
    wsRef.current = null;
  }
}

/**
 * Cleanup all WebSocket resources (connection, intervals, timeouts)
 *
 * Use this for comprehensive cleanup on component unmount or reconnection.
 *
 * @param {Object} wsRef - React ref containing WebSocket instance
 * @param {Object} reconnectTimeoutRef - React ref containing timeout ID
 * @param {Object} pingIntervalRef - React ref containing interval ID
 */
export function cleanupWebSocket(wsRef, reconnectTimeoutRef, pingIntervalRef) {
  closeWebSocket(wsRef);
  clearReconnectTimeout(reconnectTimeoutRef);
  clearPingInterval(pingIntervalRef);
}
