/**
 * Validation Helpers
 *
 * Utility functions for parsing and processing validation data.
 * Extracted from ValidationBanner to follow Single Responsibility Principle.
 * Refactored to eliminate code duplication (DRY principle).
 */

/**
 * @typedef {Object} ValidationError
 * @property {string} type - Error type label
 * @property {string} message - Error message
 */

/**
 * @typedef {Object} ValidationFieldConfig
 * @property {string} key - Field key in validation status object
 * @property {string} label - Human-readable field label
 */

/**
 * Validation field definitions for error parsing
 * Centralized configuration to avoid duplication
 * @type {ValidationFieldConfig[]}
 */
const VALIDATION_FIELDS = [
  { key: 'ftp_connection', label: 'FTP Connection' },
  { key: 'temp_path', label: 'Temp Path' },
  { key: 'output_path', label: 'Output Path' },
];

/**
 * Parse validation status into a list of errors
 *
 * Refactored to eliminate code duplication by using a configuration array.
 * This makes it easy to add new validation fields without duplicating logic.
 *
 * @param {Object|null|undefined} validationStatus - Validation status object from API
 * @returns {ValidationError[]} Array of error objects
 */
export function parseValidationErrors(validationStatus) {
  if (!validationStatus) {
    return [];
  }

  return VALIDATION_FIELDS
    .filter(field => {
      const status = validationStatus[field.key];
      return status && !status.valid;
    })
    .map(field => ({
      type: field.label,
      message: validationStatus[field.key].message
    }));
}

/**
 * Check if validation status should display banner
 *
 * @param {Object|null|undefined} validationStatus - Validation status object
 * @param {boolean} dismissed - Whether user dismissed the banner
 * @returns {boolean} True if banner should be shown
 */
export function shouldShowBanner(validationStatus, dismissed) {
  if (!validationStatus || dismissed) {
    return false;
  }

  return !validationStatus.overall_valid;
}
