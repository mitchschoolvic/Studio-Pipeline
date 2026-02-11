import { calculateBitrateKbps, formatBitrate, isBitrateValid } from '../utils/videoUtils';

/**
 * BitrateBadge Component
 * 
 * Displays a color-coded badge showing the bitrate of a video file.
 * Green badge indicates bitrate meets or exceeds threshold (good quality).
 * Red badge indicates bitrate is below threshold (poor quality/empty).
 * 
 * Responsibility: Render bitrate badge with appropriate styling and tooltip
 * 
 * @param {Object} props
 * @param {number} props.fileSize - File size in bytes
 * @param {number} props.duration - Video duration in seconds
 * @param {number} props.thresholdKbps - Minimum acceptable bitrate in kbps (default: 500)
 * @param {string} props.className - Additional CSS classes
 */
export function BitrateBadge({ fileSize, duration, thresholdKbps = 500, className = '' }) {
  // Don't render if duration is not available
  if (!duration || duration <= 0) {
    return null;
  }

  const bitrateKbps = calculateBitrateKbps(fileSize, duration);
  const isValid = isBitrateValid(bitrateKbps, thresholdKbps);
  const formattedBitrate = formatBitrate(bitrateKbps);

  // Color coding based on threshold
  const badgeClasses = isValid
    ? 'bg-green-100 text-green-700 border-green-300'
    : 'bg-red-100 text-red-700 border-red-300';

  // Tooltip message
  const tooltipMessage = isValid
    ? `Good quality: ${formattedBitrate} exceeds threshold of ${formatBitrate(thresholdKbps)}`
    : `Low quality: ${formattedBitrate} is below threshold of ${formatBitrate(thresholdKbps)}`;

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${badgeClasses} ${className}`}
      title={tooltipMessage}
    >
      <svg 
        className="w-3 h-3" 
        fill="none" 
        stroke="currentColor" 
        viewBox="0 0 24 24"
      >
        <path 
          strokeLinecap="round" 
          strokeLinejoin="round" 
          strokeWidth={2} 
          d="M13 10V3L4 14h7v7l9-11h-7z" 
        />
      </svg>
      {formattedBitrate}
    </span>
  );
}
