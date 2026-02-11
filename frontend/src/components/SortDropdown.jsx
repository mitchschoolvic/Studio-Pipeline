import { SORT_OPTIONS, SORT_OPTION_LABELS } from '../utils/sessionFilters';

/**
 * SortDropdown Component
 * 
 * Dropdown for selecting sort option.
 * Single Responsibility: Manages sort option selection only.
 * 
 * @param {string} currentSort - Current sort option value
 * @param {function} onSortChange - Callback when sort option changes
 */
export function SortDropdown({ currentSort, onSortChange }) {
  return (
    <div className="flex items-center gap-2">
      <label htmlFor="sort-select" className="text-sm font-medium text-gray-400 whitespace-nowrap">
        Sort by:
      </label>
      <select
        id="sort-select"
        value={currentSort}
        onChange={(e) => onSortChange(e.target.value)}
        className="px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-400 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-shadow cursor-pointer"
        aria-label="Sort sessions"
      >
        {SORT_OPTION_LABELS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.icon} {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
