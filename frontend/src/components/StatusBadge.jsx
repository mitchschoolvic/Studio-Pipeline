/**
 * StatusBadge Component
 *
 * Renders a small, color-coded pill indicating a status. Supports kinds:
 * - kind="server" with statuses: 'On ATEM' | 'Files Missing' | 'Deleted'
 * - kind="destination" with statuses: 'On Device' | 'Files Missing'
 * - kind="onedrive" with statuses: 'Uploaded' | 'Uploading' | 'Not Uploaded' | 'Unknown'
 */
export function StatusBadge({ kind, status, title = '', className = '' }) {
  const getClasses = () => {
    if (kind === 'server') {
      switch (status) {
        case 'On ATEM':
          return 'text-green-700 bg-green-100 border border-green-200';
        case 'Files Missing':
          return 'text-amber-700 bg-amber-100 border border-amber-200';
        case 'Deleted':
          return 'text-red-700 bg-red-100 border border-red-200';
        default:
          return 'text-gray-700 bg-gray-100 border border-gray-200';
      }
    }
    if (kind === 'onedrive') {
      switch (status) {
        case 'Uploaded':
          return 'text-blue-700 bg-blue-100 border border-blue-200';
        case 'Uploading':
          return 'text-indigo-700 bg-indigo-100 border border-indigo-200';
        case 'Not Uploaded':
          return 'text-amber-700 bg-amber-100 border border-amber-200';
        default:
          return 'text-gray-700 bg-gray-100 border border-gray-200';
      }
    }
    // destination
    switch (status) {
      case 'On Device':
        return 'text-green-700 bg-green-100 border border-green-200';
      case 'Files Missing':
        return 'text-red-700 bg-red-100 border border-red-200';
      default:
        return 'text-gray-700 bg-gray-100 border border-gray-200';
    }
  };

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${getClasses()} ${className}`}
      title={title}
    >
      {status}
    </span>
  );
}

export default StatusBadge;
