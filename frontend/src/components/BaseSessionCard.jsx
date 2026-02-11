import React from 'react';

// Minimal base wrapper for a session card, providing consistent container and expand/collapse click handling.
export function BaseSessionCard({
  isExpanded,
  onToggleExpand,
  header,
  expanded,
  cardRef,
  debugLabel,
}) {
  return (
    <div ref={cardRef} className="relative border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
      {debugLabel && (
        <div className="absolute top-0 right-0 m-1 text-[10px] px-1.5 py-0.5 rounded bg-indigo-600 text-white font-mono tracking-tight shadow">
          {debugLabel}
        </div>
      )}
      <div
        className="bg-gradient-to-r from-gray-50 to-white p-4 cursor-pointer hover:bg-gray-100 transition-colors"
        onClick={(e) => {
          if (e.target.closest('button')) return; // don't toggle on button clicks
          onToggleExpand?.();
        }}
      >
        {header}
      </div>
      {isExpanded && (
        <div className="border-top border-gray-200 bg-gray-50">
          {expanded}
        </div>
      )}
    </div>
  );
}
