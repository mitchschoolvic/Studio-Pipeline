import { Settings, CheckCircle, XCircle } from 'lucide-react';

/**
 * ValidationActions Component
 *
 * Pure presentational component for rendering validation action buttons.
 * Follows Single Responsibility Principle - only concerned with rendering action buttons.
 */
export function ValidationActions({ onOpenSettings, onRecheck, onDismiss }) {
  return (
    <div className="mt-4 flex gap-2">
      <button
        onClick={onOpenSettings}
        className="inline-flex items-center gap-1 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded transition-colors"
      >
        <Settings className="w-4 h-4" />
        Open Settings
      </button>
      <button
        onClick={onRecheck}
        className="inline-flex items-center gap-1 px-3 py-1.5 bg-white hover:bg-gray-50 text-red-700 border border-red-300 text-sm font-medium rounded transition-colors"
      >
        <CheckCircle className="w-4 h-4" />
        Recheck
      </button>
      <button
        onClick={onDismiss}
        className="inline-flex items-center gap-1 px-3 py-1.5 bg-white hover:bg-gray-50 text-gray-700 border border-gray-300 text-sm font-medium rounded transition-colors"
      >
        <XCircle className="w-4 h-4" />
        Dismiss
      </button>
    </div>
  );
}
