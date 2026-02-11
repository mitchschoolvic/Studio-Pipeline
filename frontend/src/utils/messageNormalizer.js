/**
 * WebSocket Message Normalizer
 *
 * Provides a strategy pattern for normalizing different types of WebSocket messages.
 * This follows the Open/Closed Principle - new message types can be added without
 * modifying existing code.
 */

/**
 * Default normalizer - merges data into top level
 *
 * This normalizer handles the common case where the message has a nested 'data' object
 * that should be flattened to the top level for easier access by UI components.
 *
 * @param {Object} message - Raw WebSocket message
 * @returns {Object} Normalized message with data merged to top level
 */
const defaultNormalizer = (message) => {
  if (message && message.data && typeof message.data === 'object') {
    return { type: message.type, ...message.data };
  }
  return message;
};

/**
 * Ping/Pong message normalizer
 *
 * Handles keepalive messages - no transformation needed
 *
 * @param {Object} message - Ping or pong message
 * @returns {Object} Original message unchanged
 */
const pingPongNormalizer = (message) => {
  return message;
};

/**
 * Error message normalizer
 *
 * Ensures error messages have a consistent structure
 *
 * @param {Object} message - Error message
 * @returns {Object} Normalized error message
 */
const errorNormalizer = (message) => {
  return {
    type: 'error',
    error: message.error || message.data?.error || 'Unknown error',
    details: message.details || message.data?.details || null,
    timestamp: message.timestamp || new Date().toISOString()
  };
};

/**
 * Message normalizer registry
 *
 * Maps message types to their respective normalizer functions.
 * To add support for a new message type, simply add a new entry here.
 */
const messageNormalizers = {
  ping: pingPongNormalizer,
  pong: pingPongNormalizer,
  error: errorNormalizer,
  // Add more specific normalizers here as needed
  // Example:
  // 'file.progress': fileProgressNormalizer,
  // 'job.completed': jobCompletedNormalizer,

  // Default normalizer for all other message types
  default: defaultNormalizer
};

/**
 * Normalize a WebSocket message based on its type
 *
 * This function selects the appropriate normalizer based on the message type
 * and applies it to transform the message into a consistent format.
 *
 * @param {Object} message - Raw WebSocket message
 * @returns {Object} Normalized message
 *
 * @example
 * const rawMessage = { type: 'file.progress', data: { file_id: '123', progress: 50 } };
 * const normalized = normalizeMessage(rawMessage);
 * // Result: { type: 'file.progress', file_id: '123', progress: 50 }
 */
export function normalizeMessage(message) {
  if (!message) {
    return message;
  }

  const messageType = message.type;
  const normalizer = messageNormalizers[messageType] || messageNormalizers.default;

  return normalizer(message);
}

/**
 * Register a custom normalizer for a specific message type
 *
 * This allows extending the normalizer without modifying this file,
 * following the Open/Closed Principle.
 *
 * @param {string} messageType - The message type to register a normalizer for
 * @param {Function} normalizer - The normalizer function
 *
 * @example
 * registerNormalizer('custom.event', (message) => {
 *   return { ...message, processed: true };
 * });
 */
export function registerNormalizer(messageType, normalizer) {
  if (typeof normalizer !== 'function') {
    throw new Error('Normalizer must be a function');
  }

  messageNormalizers[messageType] = normalizer;
}

/**
 * Get all registered message types
 *
 * Useful for debugging and testing
 *
 * @returns {Array<string>} Array of registered message types
 */
export function getRegisteredTypes() {
  return Object.keys(messageNormalizers).filter(type => type !== 'default');
}
