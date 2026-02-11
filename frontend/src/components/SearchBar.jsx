import { useState, useEffect } from 'react';
import { Search, X } from 'lucide-react';
import { useDebounce } from '../hooks/useDebounce';

/**
 * SearchBar Component
 * 
 * Search input with debouncing and clear functionality.
 * Single Responsibility: Manages search input only.
 * 
 * @param {function} onSearchChange - Callback when debounced search term changes
 * @param {string} placeholder - Placeholder text (optional)
 */
export function SearchBar({ onSearchChange, placeholder = 'Search sessions...' }) {
  const [localValue, setLocalValue] = useState('');
  const debouncedValue = useDebounce(localValue, 300);

  // Notify parent of debounced value changes
  useEffect(() => {
    onSearchChange(debouncedValue);
  }, [debouncedValue, onSearchChange]);

  const handleClear = () => {
    setLocalValue('');
  };

  return (
    <div className="relative flex-1 max-w-md" role="search">
      {/* Search Icon */}
      <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
        <Search className="w-4 h-4 text-gray-400" />
      </div>

      {/* Search Input */}
      <input
        type="text"
        value={localValue}
        onChange={(e) => setLocalValue(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-10 pr-10 py-2 border border-gray-300 rounded-lg text-sm text-black focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-shadow"
        aria-label="Search sessions"
      />

      {/* Clear Button */}
      {localValue && (
        <button
          onClick={handleClear}
          className="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-400 hover:text-gray-600 transition-colors"
          aria-label="Clear search"
          type="button"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
