/**
 * Session Filtering and Sorting Utilities
 * 
 * Centralized logic for filtering and sorting sessions.
 * Follows Open/Closed Principle - easy to extend with new sort options.
 */

/**
 * Sort option constants
 */
export const SORT_OPTIONS = {
  // Recording Date
  NEWEST: 'newest',
  OLDEST: 'oldest',
  // Discovery Date
  DISCOVERY_NEWEST: 'discovery_newest',
  DISCOVERY_OLDEST: 'discovery_oldest',
  // Last Updated
  LAST_UPDATED_NEWEST: 'last_updated_newest',
  LAST_UPDATED_OLDEST: 'last_updated_oldest',
  // Size
  LARGEST: 'largest',
  SMALLEST: 'smallest',
  // Queue Order
  FIRST_QUEUED: 'first_queued',
  LAST_QUEUED: 'last_queued'
};

/**
 * Sort option metadata for UI rendering
 * Grouped by category for better UX
 */
export const SORT_OPTION_LABELS = [
  // Recording Date
  { value: SORT_OPTIONS.NEWEST, label: 'Recording Date: Newest', icon: '↓', group: 'Recording Date' },
  { value: SORT_OPTIONS.OLDEST, label: 'Recording Date: Oldest', icon: '↑', group: 'Recording Date' },
  // Discovery Date
  { value: SORT_OPTIONS.DISCOVERY_NEWEST, label: 'Discovery Date: Newest', icon: '↓', group: 'Discovery Date' },
  { value: SORT_OPTIONS.DISCOVERY_OLDEST, label: 'Discovery Date: Oldest', icon: '↑', group: 'Discovery Date' },
  // Last Updated
  { value: SORT_OPTIONS.LAST_UPDATED_NEWEST, label: 'Last Updated: Newest', icon: '↓', group: 'Last Updated' },
  { value: SORT_OPTIONS.LAST_UPDATED_OLDEST, label: 'Last Updated: Oldest', icon: '↑', group: 'Last Updated' },
  // Size
  { value: SORT_OPTIONS.LARGEST, label: 'Size: Largest', icon: '⬇', group: 'Size' },
  { value: SORT_OPTIONS.SMALLEST, label: 'Size: Smallest', icon: '⬆', group: 'Size' },
  // Queue Order
  { value: SORT_OPTIONS.FIRST_QUEUED, label: 'Queue Order: First', icon: '#', group: 'Queue Order' },
  { value: SORT_OPTIONS.LAST_QUEUED, label: 'Queue Order: Last', icon: '#', group: 'Queue Order' }
];

/**
 * Filter sessions by search term
 * 
 * Searches across multiple fields:
 * - Session name (session_id)
 * - Recording date
 * - File information
 * 
 * @param {Array} sessions - Array of session objects
 * @param {string} searchTerm - Search term (case-insensitive)
 * @returns {Array} Filtered sessions
 */
export function filterSessions(sessions, searchTerm) {
  if (!searchTerm || searchTerm.trim() === '') {
    return sessions;
  }

  const term = searchTerm.toLowerCase().trim();

  return sessions.filter(session => {
    // Search in session name
    if (session.name?.toLowerCase().includes(term)) {
      return true;
    }

    // Search in recording date
    if (session.recording_date?.toLowerCase().includes(term)) {
      return true;
    }

    // Search in file names
    if (session.files && session.files.length > 0) {
      const hasMatchingFile = session.files.some(file => 
        file.filename?.toLowerCase().includes(term)
      );
      if (hasMatchingFile) {
        return true;
      }
    }

    // Search in ATEM group name if present
    if (session.atem_group_name?.toLowerCase().includes(term)) {
      return true;
    }

    return false;
  });
}

/**
 * Sort sessions by specified option
 * 
 * @param {Array} sessions - Array of session objects
 * @param {string} sortOption - One of SORT_OPTIONS values
 * @returns {Array} Sorted sessions (new array)
 */
export function sortSessions(sessions, sortOption) {
  // Create a copy to avoid mutating original array
  const sorted = [...sessions];

  switch (sortOption) {
    case SORT_OPTIONS.NEWEST:
      return sorted.sort((a, b) => {
        // Sort by recording_date and recording_time, newest first
        const dateA = getSessionDateTime(a);
        const dateB = getSessionDateTime(b);
        return dateB - dateA;
      });

    case SORT_OPTIONS.OLDEST:
      return sorted.sort((a, b) => {
        // Sort by recording_date and recording_time, oldest first
        const dateA = getSessionDateTime(a);
        const dateB = getSessionDateTime(b);
        return dateA - dateB;
      });

    case SORT_OPTIONS.LARGEST:
      return sorted.sort((a, b) => {
        // Sort by total_size, largest first
        const sizeA = a.total_size || 0;
        const sizeB = b.total_size || 0;
        return sizeB - sizeA;
      });

    case SORT_OPTIONS.SMALLEST:
      return sorted.sort((a, b) => {
        // Sort by total_size, smallest first
        const sizeA = a.total_size || 0;
        const sizeB = b.total_size || 0;
        return sizeA - sizeB;
      });

    case SORT_OPTIONS.FIRST_QUEUED:
      return sorted.sort((a, b) => {
        // Sort by minimum queue_order across all files in session (oldest first)
        const queueA = getMinQueueOrder(a);
        const queueB = getMinQueueOrder(b);
        return queueA - queueB;
      });

    case SORT_OPTIONS.LAST_QUEUED:
      return sorted.sort((a, b) => {
        // Sort by minimum queue_order across all files in session (newest first)
        const queueA = getMinQueueOrder(a);
        const queueB = getMinQueueOrder(b);
        return queueB - queueA;
      });

    case SORT_OPTIONS.DISCOVERY_NEWEST:
      return sorted.sort((a, b) => {
        // Sort by discovered_at, newest first
        const dateA = getDiscoveryDate(a);
        const dateB = getDiscoveryDate(b);
        return dateB - dateA;
      });

    case SORT_OPTIONS.DISCOVERY_OLDEST:
      return sorted.sort((a, b) => {
        // Sort by discovered_at, oldest first
        const dateA = getDiscoveryDate(a);
        const dateB = getDiscoveryDate(b);
        return dateA - dateB;
      });

    case SORT_OPTIONS.LAST_UPDATED_NEWEST:
      return sorted.sort((a, b) => {
        // Sort by most recent file updated_at, newest first
        const dateA = getLastUpdatedDate(a);
        const dateB = getLastUpdatedDate(b);
        return dateB - dateA;
      });

    case SORT_OPTIONS.LAST_UPDATED_OLDEST:
      return sorted.sort((a, b) => {
        // Sort by most recent file updated_at, oldest first
        const dateA = getLastUpdatedDate(a);
        const dateB = getLastUpdatedDate(b);
        return dateA - dateB;
      });

    default:
      return sorted;
  }
}

/**
 * Helper: Get session date/time as Date object for sorting
 *
 * @param {Object} session - Session object
 * @returns {Date} Date object
 */
function getSessionDateTime(session) {
  if (!session.recording_date) {
    return new Date(0); // Epoch for sessions without date
  }

  // Combine recording_date and recording_time if available
  let dateString = session.recording_date;
  if (session.recording_time) {
    dateString += ' ' + session.recording_time;
  }

  const date = new Date(dateString);

  // Fallback to created_at if recording_date is invalid
  if (isNaN(date.getTime()) && session.created_at) {
    return new Date(session.created_at);
  }

  return date;
}

/**
 * Helper: Get minimum queue_order from session's files
 *
 * @param {Object} session - Session object
 * @returns {number} Minimum queue_order (Infinity if no files or no queue_order)
 */
function getMinQueueOrder(session) {
  if (!session.files || session.files.length === 0) {
    return Infinity; // Sessions without files go to end
  }

  const queueOrders = session.files
    .map(file => file.queue_order)
    .filter(order => order != null && order !== undefined);

  if (queueOrders.length === 0) {
    return Infinity; // Sessions without queue_order go to end
  }

  return Math.min(...queueOrders);
}

/**
 * Helper: Get discovery date for sorting
 *
 * @param {Object} session - Session object
 * @returns {Date} Discovery date
 */
function getDiscoveryDate(session) {
  if (!session.discovered_at) {
    return new Date(0); // Epoch for sessions without discovery date
  }

  const date = new Date(session.discovered_at);

  // Fallback to created_at if discovered_at is invalid
  if (isNaN(date.getTime()) && session.created_at) {
    return new Date(session.created_at);
  }

  return date;
}

/**
 * Helper: Get most recent file updated_at date for sorting
 *
 * @param {Object} session - Session object
 * @returns {Date} Most recent file updated date
 */
function getLastUpdatedDate(session) {
  if (!session.files || session.files.length === 0) {
    // Fallback to session's created_at or epoch
    if (session.created_at) {
      return new Date(session.created_at);
    }
    return new Date(0);
  }

  // Find most recent updated_at among all files
  const dates = session.files
    .map(file => file.updated_at ? new Date(file.updated_at) : null)
    .filter(date => date && !isNaN(date.getTime()));

  if (dates.length === 0) {
    // Fallback to session's created_at or epoch
    if (session.created_at) {
      return new Date(session.created_at);
    }
    return new Date(0);
  }

  // Return the most recent date
  return new Date(Math.max(...dates.map(d => d.getTime())));
}
