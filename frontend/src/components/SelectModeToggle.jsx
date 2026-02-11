import { CheckSquare } from 'lucide-react';

/**
 * SelectModeToggle Component
 * 
 * Button to enter select mode.
 * Placed in the session list header.
 */
export function SelectModeToggle({ onToggle, isSelectMode }) {
  if (isSelectMode) {
    return null; // Don't show when already in select mode
  }

  return (
    <button
      onClick={onToggle}
      className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white transition-colors font-medium text-sm"
      title="Enter select mode to perform bulk operations"
    >
      <CheckSquare className="w-4 h-4" />
      <span>Select</span>
    </button>
  );
}
