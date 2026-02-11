import { useState } from 'react';
import { X, Trash2, AlertCircle, RefreshCw, CheckSquare, Square, AlertTriangle, Mic, Brain, GraduationCap, Tag, ChevronDown } from 'lucide-react';

// Faculty options
const FACULTY_OPTIONS = [
  'Whole School', 'Humanities', 'English', 'Commerce', 'PE',
  'Languages', 'Visual Arts', 'Sciences', 'Music'
];

// Content Type options
const CONTENT_TYPE_OPTIONS = [
  'Guidance & Information', 'Promotional', 'Learning Content',
  'Student Work', 'Out-take/Noise', 'Announcements'
];

/**
 * SelectModeToolbar Component
 *
 * Appears at the top when select mode is active.
 * Shows:
 * - Selected count
 * - Select All / Deselect All buttons
 * - Action buttons (Mark for FTP Deletion, Remove from Database, Clear Missing, Retry Processing, Re-transcribe, Re-analyze)
 * - Cancel button to exit select mode
 */
export function SelectModeToolbar({
  selectedCount,
  totalCount,
  onSelectAll,
  onDeselectAll,
  onMarkForDeletion,
  onRemoveFromDatabase,
  onClearMissing,
  onRetryProcessing,
  onReTranscribe,
  onReAnalyze,
  onChangeFaculty,
  onChangeContentType,
  onCancel,
  activeTab
}) {
  const [showFacultyDropdown, setShowFacultyDropdown] = useState(false);
  const [showContentTypeDropdown, setShowContentTypeDropdown] = useState(false);
  
  const allSelected = selectedCount === totalCount && totalCount > 0;
  const hasSelection = selectedCount > 0;

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 shadow-sm mb-4 animate-fadeIn">
      <div className="flex items-center justify-between">
        {/* Left: Selection count and select all/deselect */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-blue-900">
              {selectedCount} {selectedCount === 1 ? 'session' : 'sessions'} selected
            </span>
            {totalCount > 0 && (
              <span className="text-sm text-blue-700">
                of {totalCount}
              </span>
            )}
          </div>

          {totalCount > 0 && (
            <button
              onClick={allSelected ? onDeselectAll : onSelectAll}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-white hover:bg-blue-100 border border-blue-300 rounded text-sm text-blue-700 transition-colors"
              title={allSelected ? 'Deselect all sessions' : 'Select all sessions'}
            >
              {allSelected ? (
                <>
                  <Square className="w-4 h-4" />
                  <span>Deselect All</span>
                </>
              ) : (
                <>
                  <CheckSquare className="w-4 h-4" />
                  <span>Select All</span>
                </>
              )}
            </button>
          )}
        </div>

        {/* Right: Action buttons and cancel */}
        <div className="flex items-center gap-2">
          {/* Action Buttons */}
          <div className="flex items-center gap-2">
            {/* Retry Processing - only on failed tab or if has failed files */}
            {activeTab === 'failed' && (
              <button
                onClick={onRetryProcessing}
                disabled={!hasSelection}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${hasSelection
                    ? 'bg-blue-600 hover:bg-blue-700 text-white'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                  }`}
                title="Retry processing for selected sessions"
              >
                <RefreshCw className="w-4 h-4" />
                <span>Retry Processing</span>
              </button>
            )}

            {/* Clear Missing - only on missing tab */}
            {activeTab === 'missing' && (
              <button
                onClick={onClearMissing}
                disabled={!hasSelection}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${hasSelection
                    ? 'bg-orange-600 hover:bg-orange-700 text-white'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                  }`}
                title="Clear missing files for selected sessions"
              >
                <AlertCircle className="w-4 h-4" />
                <span>Clear Missing</span>
              </button>
            )}

            {/* Re-transcribe - only on analytics tab */}
            {activeTab === 'analytics' && (
              <button
                onClick={onReTranscribe}
                disabled={!hasSelection}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${hasSelection
                    ? 'bg-blue-600 hover:bg-blue-700 text-white'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                  }`}
                title="Re-transcribe selected sessions with current Whisper settings"
              >
                <Mic className="w-4 h-4" />
                <span>Re-transcribe {selectedCount > 0 ? selectedCount : ''} {selectedCount === 1 ? 'item' : 'items'}</span>
              </button>
            )}

            {/* Re-analyze - only on analytics tab */}
            {activeTab === 'analytics' && (
              <button
                onClick={onReAnalyze}
                disabled={!hasSelection}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${hasSelection
                    ? 'bg-purple-600 hover:bg-purple-700 text-white'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                  }`}
                title="Re-analyze selected sessions with current LLM prompts"
              >
                <Brain className="w-4 h-4" />
                <span>Re-analyze {selectedCount > 0 ? selectedCount : ''} {selectedCount === 1 ? 'item' : 'items'}</span>
              </button>
            )}

            {/* Change Faculty Dropdown - only on analytics tab */}
            {activeTab === 'analytics' && (
              <div className="relative">
                <button
                  onClick={() => {
                    setShowFacultyDropdown(!showFacultyDropdown);
                    setShowContentTypeDropdown(false);
                  }}
                  disabled={!hasSelection}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${hasSelection
                      ? 'bg-emerald-600 hover:bg-emerald-700 text-white'
                      : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    }`}
                  title="Change faculty for selected items"
                >
                  <GraduationCap className="w-4 h-4" />
                  <span>Change Faculty</span>
                  <ChevronDown className="w-4 h-4" />
                </button>
                {showFacultyDropdown && hasSelection && (
                  <div className="absolute top-full left-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 min-w-[180px]">
                    {FACULTY_OPTIONS.map((faculty) => (
                      <button
                        key={faculty}
                        onClick={() => {
                          onChangeFaculty?.(faculty);
                          setShowFacultyDropdown(false);
                        }}
                        className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-emerald-50 hover:text-emerald-700 first:rounded-t-lg last:rounded-b-lg"
                      >
                        {faculty}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Change Content Type Dropdown - only on analytics tab */}
            {activeTab === 'analytics' && (
              <div className="relative">
                <button
                  onClick={() => {
                    setShowContentTypeDropdown(!showContentTypeDropdown);
                    setShowFacultyDropdown(false);
                  }}
                  disabled={!hasSelection}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${hasSelection
                      ? 'bg-amber-600 hover:bg-amber-700 text-white'
                      : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    }`}
                  title="Change content type for selected items"
                >
                  <Tag className="w-4 h-4" />
                  <span>Change Content Type</span>
                  <ChevronDown className="w-4 h-4" />
                </button>
                {showContentTypeDropdown && hasSelection && (
                  <div className="absolute top-full left-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 min-w-[200px]">
                    {CONTENT_TYPE_OPTIONS.map((contentType) => (
                      <button
                        key={contentType}
                        onClick={() => {
                          onChangeContentType?.(contentType);
                          setShowContentTypeDropdown(false);
                        }}
                        className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-amber-50 hover:text-amber-700 first:rounded-t-lg last:rounded-b-lg"
                      >
                        {contentType}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Mark for FTP Deletion - available on all tabs except 'deleted' and 'analytics' */}
            {activeTab !== 'deleted' && activeTab !== 'analytics' && (
              <button
                onClick={onMarkForDeletion}
                disabled={!hasSelection}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${hasSelection
                    ? 'bg-red-600 hover:bg-red-700 text-white'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                  }`}
                title="Mark selected sessions for FTP deletion"
              >
                <Trash2 className="w-4 h-4" />
                <span>Mark for FTP Deletion</span>
              </button>
            )}

            {/* Remove from Database - available on all tabs except 'deleted' */}
            {activeTab !== 'deleted' && (
              <button
                onClick={onRemoveFromDatabase}
                disabled={!hasSelection}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${hasSelection
                    ? 'bg-orange-600 hover:bg-orange-700 text-white'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                  }`}
                title="Remove selected sessions from database"
              >
                <AlertTriangle className="w-4 h-4" />
                <span>Delete from Database</span>
              </button>
            )}
          </div>

          {/* Cancel Button */}
          <button
            onClick={onCancel}
            className="flex items-center gap-2 px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded-lg text-sm font-medium text-gray-700 transition-colors ml-2"
            title="Exit select mode"
          >
            <X className="w-4 h-4" />
            <span>Cancel</span>
          </button>
        </div>
      </div>
    </div>
  );
}
