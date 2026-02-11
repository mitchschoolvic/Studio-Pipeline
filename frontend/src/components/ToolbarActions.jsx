import { Trash2, RefreshCw } from 'lucide-react';
import { SelectModeToggle } from './SelectModeToggle';

/**
 * ToolbarActions Component
 * 
 * Action buttons for the session toolbar.
 * Single Responsibility: Renders and manages action buttons only.
 * 
 * @param {boolean} isSelectMode - Whether select mode is active
 * @param {function} onToggleSelectMode - Toggle select mode callback
 * @param {function} onClearMissing - Clear missing files callback
 * @param {function} onRetryFailed - Retry failed jobs callback
 * @param {number} missingCount - Count of missing files
 * @param {number} failedCount - Count of failed files
 * @param {boolean} showClearMissing - Whether to show clear missing button
 * @param {boolean} showRetryFailed - Whether to show retry failed button
 * @param {number} totalSessions - Total number of sessions (for select button visibility)
 */
export function ToolbarActions({
  isSelectMode,
  onToggleSelectMode,
  onClearMissing,
  onRetryFailed,
  missingCount,
  failedCount,
  showClearMissing,
  showRetryFailed,
  totalSessions
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* Select Mode Toggle - hide when in select mode or no sessions */}
      {!isSelectMode && totalSessions > 0 && (
        <SelectModeToggle
          onToggle={onToggleSelectMode}
          isSelectMode={isSelectMode}
        />
      )}

      {/* Clear All Missing - only show when not in select mode, on appropriate tab, and has missing files */}
      {!isSelectMode && showClearMissing && missingCount > 0 && (
        <button
          onClick={onClearMissing}
          className="flex items-center gap-2 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium transition-colors"
          title={`Delete ${missingCount} missing file(s) from database`}
        >
          <Trash2 className="w-4 h-4" />
          <span className="hidden sm:inline">Clear All Missing</span>
          <span className="sm:hidden">Clear Missing</span>
          <span className="bg-red-700 px-1.5 py-0.5 rounded text-xs">
            {missingCount}
          </span>
        </button>
      )}

      {/* Retry All Failed - only show when not in select mode, on appropriate tab, and has failed files */}
      {!isSelectMode && showRetryFailed && failedCount > 0 && (
        <button
          onClick={onRetryFailed}
          className="flex items-center gap-2 px-3 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg text-sm font-medium transition-colors"
          title={`Retry ${failedCount} failed file(s)`}
        >
          <RefreshCw className="w-4 h-4" />
          <span className="hidden sm:inline">Retry All Failed</span>
          <span className="sm:hidden">Retry Failed</span>
          <span className="bg-orange-700 px-1.5 py-0.5 rounded text-xs">
            {failedCount}
          </span>
        </button>
      )}
    </div>
  );
}
