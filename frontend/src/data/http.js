/**
 * ETag cache for HTTP caching
 * Maps URL -> ETag value
 */
const etagCache = new Map();

/**
 * HTTP fetch wrapper with ETag support for 304 Not Modified responses
 *
 * @param {string} url - The URL to fetch
 * @param {RequestInit} init - Fetch options
 * @returns {Promise<any>} - Parsed JSON response or undefined for 304
 */
export async function httpJson(url, init = {}) {
  const headers = new Headers(init.headers || {});

  // Add stored ETag if available
  const cached = etagCache.get(url);
  if (cached && cached.etag) {
    headers.set('If-None-Match', cached.etag);
  }

  // Perform fetch
  const res = await fetch(url, { ...init, headers });

  // Handle 304 Not Modified - Return cached data
  if (res.status === 304) {
    if (cached && cached.data) {
      return cached.data;
    }
    // Fallback if we have ETag but lost data (unlikely but safe)
    return undefined;
  }

  // Handle errors
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(errorText || `HTTP ${res.status}: ${res.statusText}`);
  }

  // Parse JSON
  const data = await res.json();

  // Store new ETag and Data if present
  const newEtag = res.headers.get('ETag');
  if (newEtag) {
    etagCache.set(url, { etag: newEtag, data });
  }

  return data;
}

/**
 * Clear ETag cache for a specific URL or all URLs
 * @param {string} [url] - Optional URL to clear. If omitted, clears all.
 */
export function clearEtagCache(url) {
  if (url) {
    etagCache.delete(url);
  } else {
    etagCache.clear();
  }
}
