import { Check } from 'lucide-react';

/**
 * SessionCheckbox Component
 * 
 * A checkbox that appears in select mode for each session.
 * Provides visual feedback for selection state.
 */
export function SessionCheckbox({ isSelected, onChange, sessionId }) {
  return (
    <div 
      className="flex-shrink-0"
      onClick={(e) => {
        e.stopPropagation(); // Prevent session expansion
        onChange(sessionId);
      }}
    >
      <div
        className={`w-5 h-5 rounded border-2 flex items-center justify-center cursor-pointer transition-all duration-150 ${
          isSelected
            ? 'bg-blue-600 border-blue-600'
            : 'bg-white border-gray-300 hover:border-blue-400'
        }`}
        role="checkbox"
        aria-checked={isSelected}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === ' ' || e.key === 'Enter') {
            e.preventDefault();
            e.stopPropagation();
            onChange(sessionId);
          }
        }}
      >
        {isSelected && (
          <Check className="w-3.5 h-3.5 text-white" strokeWidth={3} />
        )}
      </div>
    </div>
  );
}
