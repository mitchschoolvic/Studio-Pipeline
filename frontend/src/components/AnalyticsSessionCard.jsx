import React from 'react';
import { ChevronRight } from 'lucide-react';
import { FileThumbnail } from './FileThumbnail';
import { BaseSessionCard } from './BaseSessionCard';
import { formatDateTime } from '../utils/dateUtils';

// Minimal Analytics variant that focuses on analytics status in the header.
export function AnalyticsSessionCard({ session, analyticsStatus = 'none', isExpanded, onToggleExpand, expandedContent }) {
  const files = Array.isArray(session.files) ? session.files : [];
  const programFile = files.find(f => f.is_program_output);
  const labels = { none:'No Analytics', pending:'Pending', transcribing:'Transcribing', analyzing:'Analyzing', completed:'Completed', failed:'Failed' };
  const colors = { none:'bg-gray-100 text-gray-500', pending:'bg-blue-100 text-blue-600', transcribing:'bg-yellow-100 text-yellow-700', analyzing:'bg-purple-100 text-purple-600', completed:'bg-green-100 text-green-700', failed:'bg-red-100 text-red-600' };

  const header = (
    <div className="flex items-center gap-3">
      <div className={`transform transition-transform ${isExpanded ? 'rotate-90' : ''}`}>
        <ChevronRight className="w-4 h-4 text-gray-500" />
      </div>
      <div className="w-24">
        {programFile ? (
          <FileThumbnail fileId={programFile.id} isEmpty={programFile.is_empty} className="w-24 rounded overflow-hidden shadow-sm" />
        ) : (
          <div className="w-24 rounded overflow-hidden bg-gray-200" style={{ aspectRatio:'16/9' }} />
        )}
      </div>
      <div className="flex-1">
        <div className="flex items-center gap-3">
          <h3 className="font-semibold text-gray-800">{session.name}</h3>
          <span className="text-xs text-gray-500">{formatDateTime(session.recording_date, session.recording_time)}</span>
        </div>
        <div className={`inline-flex mt-1 text-xs px-2 py-0.5 rounded ${colors[analyticsStatus] || colors.none}`}>
          {labels[analyticsStatus] || 'Unknown'}
        </div>
      </div>
    </div>
  );

  return (
    <BaseSessionCard
      isExpanded={isExpanded}
      onToggleExpand={onToggleExpand}
      header={header}
      expanded={expandedContent}
    />
  );
}
