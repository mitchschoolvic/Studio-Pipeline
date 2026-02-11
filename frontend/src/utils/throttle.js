/**
 * Throttle function execution
 * Ensures function is called at most once per interval
 *
 * @param {Function} func - Function to throttle
 * @param {number} delay - Minimum time between calls (ms)
 * @returns {Function} Throttled function
 */
export function throttle(func, delay) {
  let lastCall = 0;
  let timeout = null;

  return function throttled(...args) {
    const now = Date.now();
    const timeSinceLastCall = now - lastCall;

    if (timeSinceLastCall >= delay) {
      lastCall = now;
      func.apply(this, args);
    } else {
      // Schedule call for end of throttle period
      if (timeout) clearTimeout(timeout);
      timeout = setTimeout(() => {
        lastCall = Date.now();
        func.apply(this, args);
      }, delay - timeSinceLastCall);
    }
  };
}

/**
 * Debounce function execution
 * Delays execution until calls stop for specified duration
 *
 * @param {Function} func - Function to debounce
 * @param {number} delay - Delay before execution (ms)
 * @returns {Function} Debounced function
 */
export function debounce(func, delay) {
  let timeout = null;

  return function debounced(...args) {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => {
      func.apply(this, args);
    }, delay);
  };
}

/**
 * Create a request deduplicator
 * Prevents duplicate requests while one is in flight
 *
 * @returns {Function} Deduplication function
 */
export function createRequestDeduplicator() {
  const pending = new Map();

  return async function deduplicate(key, requestFn) {
    // Return existing promise if request is in flight
    if (pending.has(key)) {
      console.log(`⏭️ Deduplicating request: ${key}`);
      return pending.get(key);
    }

    // Execute new request
    const promise = requestFn()
      .finally(() => {
        pending.delete(key);
      });

    pending.set(key, promise);
    return promise;
  };
}

/**
 * Create a rate limiter that limits function calls to N per time window
 *
 * @param {Function} func - Function to rate limit
 * @param {number} maxCalls - Maximum calls per window
 * @param {number} windowMs - Time window in milliseconds
 * @returns {Function} Rate limited function
 */
export function rateLimit(func, maxCalls, windowMs) {
  const calls = [];

  return function rateLimited(...args) {
    const now = Date.now();

    // Remove calls outside the current window
    while (calls.length > 0 && calls[0] < now - windowMs) {
      calls.shift();
    }

    // Check if we're at the limit
    if (calls.length < maxCalls) {
      calls.push(now);
      return func.apply(this, args);
    } else {
      console.log(`⏸️ Rate limit reached (${maxCalls} calls per ${windowMs}ms)`);
      return null;
    }
  };
}
