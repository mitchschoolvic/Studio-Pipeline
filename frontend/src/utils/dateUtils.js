/**
 * Date formatting utilities for the application
 */

/**
 * Formats a date and time into a human-readable string with full date
 * @param {string} date - Date string (YYYY-MM-DD)
 * @param {string} time - Time string (HH:MM:SS)
 * @param {string} locale - Locale string (default: 'en-US')
 * @returns {string} Formatted date-time string
 */
export const formatDateTime = (date, time, locale = 'en-US') => {
  try {
    const d = new Date(`${date}T${time}`);
    return d.toLocaleString(locale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  } catch {
    return `${date} ${time}`;
  }
};

/**
 * Formats a timestamp into a relative time string (e.g., "Just now", "5 minutes ago")
 * @param {string|Date} timestamp - ISO timestamp or Date object
 * @returns {string} Relative time string
 */
export const getRelativeTime = (timestamp) => {
  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    const now = new Date();
    const diffMs = now - date;
    const diffSeconds = Math.floor(diffMs / 1000);
    const diffMinutes = Math.floor(diffSeconds / 60);
    const diffHours = Math.floor(diffMinutes / 60);
    const diffDays = Math.floor(diffHours / 24);
    const diffWeeks = Math.floor(diffDays / 7);
    const diffMonths = Math.floor(diffDays / 30);
    const diffYears = Math.floor(diffDays / 365);

    if (diffSeconds < 30) {
      return 'Just now';
    } else if (diffSeconds < 60) {
      return `${diffSeconds} seconds ago`;
    } else if (diffMinutes === 1) {
      return '1 minute ago';
    } else if (diffMinutes < 60) {
      return `${diffMinutes} minutes ago`;
    } else if (diffHours === 1) {
      return '1 hour ago';
    } else if (diffHours < 24) {
      return `${diffHours} hours ago`;
    } else if (diffDays === 1) {
      return '1 day ago';
    } else if (diffDays < 7) {
      return `${diffDays} days ago`;
    } else if (diffWeeks === 1) {
      return '1 week ago';
    } else if (diffWeeks < 4) {
      return `${diffWeeks} weeks ago`;
    } else if (diffMonths === 1) {
      return '1 month ago';
    } else if (diffMonths < 12) {
      return `${diffMonths} months ago`;
    } else if (diffYears === 1) {
      return '1 year ago';
    } else {
      return `${diffYears} years ago`;
    }
  } catch {
    return 'Unknown';
  }
};

/**
 * Formats date and time strings into a relative time string
 * @param {string} date - Date string (YYYY-MM-DD)
 * @param {string} time - Time string (HH:MM:SS)
 * @returns {string} Relative time string
 */
export const getRelativeTimeFromDateTime = (date, time) => {
  try {
    const timestamp = new Date(`${date}T${time}`);
    return getRelativeTime(timestamp);
  } catch {
    return 'Unknown';
  }
};

/**
 * Formats an ISO timestamp string into a human-readable date-time string
 * @param {string} isoTimestamp - ISO 8601 timestamp string
 * @param {string} locale - Locale string (default: 'en-US')
 * @returns {string} Formatted date-time string
 */
export const formatISOTimestamp = (isoTimestamp, locale = 'en-US') => {
  try {
    if (!isoTimestamp) return 'Unknown date';
    const date = new Date(isoTimestamp);
    if (isNaN(date.getTime())) return 'Unknown date';

    return date.toLocaleString(locale, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  } catch {
    return 'Unknown date';
  }
};
