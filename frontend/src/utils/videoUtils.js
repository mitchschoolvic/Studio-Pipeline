/**
 * Video file utility functions
 * 
 * Provides helper functions for video file calculations and formatting
 * following Single Responsibility Principle.
 */

/**
 * Calculate bitrate in kbps from file size and duration
 * 
 * @param {number} sizeBytes - File size in bytes
 * @param {number} durationSeconds - Video duration in seconds
 * @returns {number} Bitrate in kbps, or 0 if duration is invalid
 */
export function calculateBitrateKbps(sizeBytes, durationSeconds) {
  if (!durationSeconds || durationSeconds <= 0) {
    return 0;
  }
  
  // bitrate (kbps) = (file_size_bytes * 8) / (duration_seconds * 1000)
  return (sizeBytes * 8) / (durationSeconds * 1000);
}

/**
 * Calculate bitrate in Mbps from file size and duration
 * 
 * @param {number} sizeBytes - File size in bytes
 * @param {number} durationSeconds - Video duration in seconds
 * @returns {number} Bitrate in Mbps, or 0 if duration is invalid
 */
export function calculateBitrateMbps(sizeBytes, durationSeconds) {
  return calculateBitrateKbps(sizeBytes, durationSeconds) / 1000;
}

/**
 * Format bitrate for display
 * 
 * @param {number} bitrateKbps - Bitrate in kbps
 * @returns {string} Formatted bitrate string (e.g., "2.5 Mbps" or "750 kbps")
 */
export function formatBitrate(bitrateKbps) {
  if (bitrateKbps === 0) {
    return 'N/A';
  }
  
  if (bitrateKbps >= 1000) {
    return `${(bitrateKbps / 1000).toFixed(1)} Mbps`;
  }
  
  return `${Math.round(bitrateKbps)} kbps`;
}

/**
 * Determine if bitrate meets the quality threshold
 * 
 * @param {number} bitrateKbps - Bitrate in kbps
 * @param {number} thresholdKbps - Minimum acceptable bitrate in kbps
 * @returns {boolean} True if bitrate meets or exceeds threshold
 */
export function isBitrateValid(bitrateKbps, thresholdKbps) {
  return bitrateKbps >= thresholdKbps;
}
