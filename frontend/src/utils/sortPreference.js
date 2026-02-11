/**
 * Sort Preference Utilities
 *
 * Manages persistent sort preferences using localStorage.
 * Shared between Pipeline and Analytics tabs.
 */

const STORAGE_KEY = 'unified_sort_preference';

/**
 * Default sort preference
 */
const DEFAULT_PREFERENCE = {
  sortType: 'NEWEST', // Recording Date - Newest
  direction: 'desc'
};

/**
 * Get current sort preference from localStorage
 * @returns {{ sortType: string, direction: 'asc' | 'desc' }}
 */
export function getSortPreference() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      // Validate structure
      if (parsed.sortType && (parsed.direction === 'asc' || parsed.direction === 'desc')) {
        return parsed;
      }
    }
  } catch (error) {
    console.warn('[sortPreference] Failed to read from localStorage:', error);
  }

  return DEFAULT_PREFERENCE;
}

/**
 * Save sort preference to localStorage
 * @param {string} sortType - Sort type key (e.g., 'NEWEST', 'DISCOVERY_NEWEST')
 * @param {'asc' | 'desc'} direction - Sort direction
 */
export function setSortPreference(sortType, direction) {
  try {
    const preference = { sortType, direction };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preference));

    // Dispatch storage event for cross-tab sync
    window.dispatchEvent(new StorageEvent('storage', {
      key: STORAGE_KEY,
      newValue: JSON.stringify(preference),
      storageArea: localStorage
    }));
  } catch (error) {
    console.warn('[sortPreference] Failed to write to localStorage:', error);
  }
}

/**
 * Listen for sort preference changes (from other tabs or same tab)
 * @param {Function} callback - Called when preference changes
 * @returns {Function} Cleanup function to remove listener
 */
export function onSortPreferenceChange(callback) {
  const handler = (event) => {
    if (event.key === STORAGE_KEY && event.newValue) {
      try {
        const preference = JSON.parse(event.newValue);
        callback(preference);
      } catch (error) {
        console.warn('[sortPreference] Failed to parse storage event:', error);
      }
    }
  };

  window.addEventListener('storage', handler);

  return () => {
    window.removeEventListener('storage', handler);
  };
}
