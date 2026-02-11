import { List, LayoutGrid, ChevronLeft, ChevronRight, GraduationCap, Video } from 'lucide-react';
import { SearchBar } from './SearchBar';
import { SortDropdown } from './SortDropdown';
import { ToolbarActions } from './ToolbarActions';
import { useSelectMode } from '../contexts/SelectModeContext';

// Faculty options for filtering
const FACULTY_OPTIONS = [
  'Whole School', 'Humanities', 'English', 'Commerce', 'PE',
  'Languages', 'Visual Arts', 'Sciences', 'Music'
];

// Content Type options for filtering
const CONTENT_TYPE_OPTIONS = [
  'Guidance & Information', 'Promotional', 'Learning Content',
  'Student Work', 'Out-take/Noise', 'Announcements'
];

/**
 * SessionToolbar Component
 * 
 * Unified toolbar above session list that composes:
 * - SearchBar (search/filter)
 * - SortDropdown (sort options)
 * - Faculty Filter (analytics view)
 * - View Mode Toggle (Pipeline/Analytics)
 * - Layout Toggle (List/Grid)
 * - Term Selector (for grid view)
 * - ToolbarActions (action buttons)
 * 
 * Single Responsibility: Layout and composition of toolbar children.
 */
export function SessionToolbar({
  searchTerm,
  onSearchChange,
  sortOption,
  onSortChange,
  showClearMissing,
  showRetryFailed,
  missingCount,
  failedCount,
  onClearMissing,
  onRetryFailed,
  totalSessions,
  // View mode props
  viewMode,
  onViewModeChange,
  // AI enabled flag - determines if analytics toggle is shown
  aiEnabled = false,
  // Layout props
  layoutView,
  onLayoutViewChange,
  // Term selector props
  selectedTerm,
  onSelectedTermChange,
  availableTerms = [],
  // Faculty filter props
  facultyFilter,
  onFacultyFilterChange,
  // Content Type filter props
  contentTypeFilter,
  onContentTypeFilterChange
}) {
  const selectMode = useSelectMode();

  return (
    <div 
      className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-10"
      role="toolbar"
      aria-label="Session list controls"
    >
      <div className="p-3 sm:p-4">
        {/* Main toolbar row */}
        <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 sm:items-center">
          {/* Left side: Search and Sort */}
          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 flex-1 sm:items-center">
            <SearchBar 
              onSearchChange={onSearchChange}
              placeholder="Search by name, title, or description..."
            />
            
            <SortDropdown
              currentSort={sortOption}
              onSortChange={onSortChange}
            />

            {/* Faculty Filter - only in analytics view */}
            {viewMode === 'analytics' && (
              <div className="flex items-center gap-2">
                <GraduationCap className="w-4 h-4 text-gray-400" />
                <select
                  value={facultyFilter || ''}
                  onChange={(e) => onFacultyFilterChange?.(e.target.value || null)}
                  className="px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent min-w-[140px]"
                >
                  <option value="">All Faculties</option>
                  {FACULTY_OPTIONS.map(faculty => (
                    <option key={faculty} value={faculty}>
                      {faculty}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Content Type Filter - only in analytics view */}
            {viewMode === 'analytics' && (
              <div className="flex items-center gap-2">
                <Video className="w-4 h-4 text-gray-400" />
                <select
                  value={contentTypeFilter || ''}
                  onChange={(e) => onContentTypeFilterChange?.(e.target.value || null)}
                  className="px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent min-w-[160px]"
                >
                  <option value="">All Content Types</option>
                  {CONTENT_TYPE_OPTIONS.map(contentType => (
                    <option key={contentType} value={contentType}>
                      {contentType}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Center: View toggles */}
          {viewMode !== undefined && (
            <div className="flex items-center gap-2">
              {/* Pipeline/Analytics Toggle - only shown when AI is enabled */}
              {aiEnabled && (
                <div className="bg-gray-200 p-1 rounded-lg inline-flex items-center">
                  <button
                    onClick={() => onViewModeChange?.('pipeline')}
                    className={`px-3 py-1 rounded-md text-sm font-medium transition-all ${viewMode === 'pipeline'
                      ? 'bg-white text-gray-900 shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    Pipeline
                  </button>
                  <button
                    onClick={() => onViewModeChange?.('analytics')}
                    className={`px-3 py-1 rounded-md text-sm font-medium transition-all ${viewMode === 'analytics'
                      ? 'bg-white text-gray-900 shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    Analytics
                  </button>
                </div>
              )}

              {/* List/Grid Layout Toggle */}
              <div className="bg-gray-200 p-1 rounded-lg inline-flex items-center">
                <button
                  onClick={() => onLayoutViewChange?.('list')}
                  className={`p-1.5 rounded-md transition-all ${layoutView === 'list'
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                  }`}
                  title="List View"
                >
                  <List className="w-4 h-4" />
                </button>
                <button
                  onClick={() => onLayoutViewChange?.('grid')}
                  className={`p-1.5 rounded-md transition-all ${layoutView === 'grid'
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                  }`}
                  title="Grid View"
                >
                  <LayoutGrid className="w-4 h-4" />
                </button>
              </div>

              {/* Term Selector (Grid View Only) */}
              {layoutView === 'grid' && availableTerms.length > 0 && (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => {
                      const currentIndex = selectedTerm 
                        ? availableTerms.findIndex(t => t.key === selectedTerm)
                        : -1;
                      if (currentIndex < availableTerms.length - 1) {
                        onSelectedTermChange?.(availableTerms[currentIndex + 1].key);
                      }
                    }}
                    disabled={selectedTerm === availableTerms[availableTerms.length - 1]?.key}
                    className="p-1 rounded hover:bg-gray-200 disabled:opacity-30 disabled:cursor-not-allowed text-gray-600"
                    title="Previous Term"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  
                  <select
                    value={selectedTerm || ''}
                    onChange={(e) => onSelectedTermChange?.(e.target.value || null)}
                    className="px-2 py-1 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent min-w-[140px]"
                  >
                    <option value="">All Terms</option>
                    {availableTerms.map(term => (
                      <option key={term.key} value={term.key}>
                        {term.label} ({term.count})
                      </option>
                    ))}
                  </select>
                  
                  <button
                    onClick={() => {
                      const currentIndex = selectedTerm 
                        ? availableTerms.findIndex(t => t.key === selectedTerm)
                        : availableTerms.length;
                      if (currentIndex > 0) {
                        onSelectedTermChange?.(availableTerms[currentIndex - 1].key);
                      } else if (!selectedTerm && availableTerms.length > 0) {
                        onSelectedTermChange?.(availableTerms[0].key);
                      }
                    }}
                    disabled={!selectedTerm || selectedTerm === availableTerms[0]?.key}
                    className="p-1 rounded hover:bg-gray-200 disabled:opacity-30 disabled:cursor-not-allowed text-gray-600"
                    title="Next Term"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Right side: Actions */}
          <ToolbarActions
            isSelectMode={selectMode.isSelectMode}
            onToggleSelectMode={selectMode.toggleSelectMode}
            onClearMissing={onClearMissing}
            onRetryFailed={onRetryFailed}
            missingCount={missingCount}
            failedCount={failedCount}
            showClearMissing={showClearMissing}
            showRetryFailed={showRetryFailed}
            totalSessions={totalSessions}
          />
        </div>

        {/* Session count indicator */}
        {totalSessions > 0 && (
          <div className="mt-2 text-xs text-gray-500">
            {totalSessions} {totalSessions === 1 ? 'session' : 'sessions'}
            {searchTerm && ' (filtered)'}
          </div>
        )}
      </div>
    </div>
  );
}
