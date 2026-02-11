
import React from 'react';
import { X, Calendar, User, Users, Tag, Clock, Video, FolderOpen } from 'lucide-react';
import { useAnalyticsSummary, useAnalyticsDrilldown } from '../api/analytics';
import { FileThumbnail } from './FileThumbnail';

export function AnalyticsDrillDownModal({ isOpen, onClose, title, timeRange, filterType, filterValue, filters }) {
    if (!isOpen) return null;

    // Strategy: Use dedicated drilldown hook if type/value are present (Categories)
    // Otherwise fallback to summary hook (Date ranges)
    const isDrilldown = !!filterType && !!filterValue;

    const drilldownQuery = useAnalyticsDrilldown(timeRange, filterType, filterValue);

    // Fallback for date-range queries (Volume chart)
    const summaryQuery = useAnalyticsSummary({
        ...filters,
        pageSize: 1000
    });

    // Select active query
    const { data: summaryData, isLoading, error } = isDrilldown ? drilldownQuery : summaryQuery;

    const handleOpenFolder = async (e, sessionId) => {
        e.stopPropagation();
        if (!sessionId) return;
        try {
            const resp = await fetch(`/api/sessions/${sessionId}/open-folder`, { method: 'POST' });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                alert(`Failed to open folder: ${err.detail || 'Unknown error'}`);
            }
        } catch (err) {
            alert('Failed to open folder');
        }
    };

    return (
        <div
            className="fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50"
            onClick={onClose}
        >
            <div
                className="bg-white rounded-xl shadow-2xl w-full max-w-4xl h-[80vh] flex flex-col overflow-hidden"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="h-16 bg-white border-b border-gray-200 flex items-center px-6 justify-between shrink-0">
                    <div>
                        <h2 className="text-xl font-bold text-gray-800">{title}</h2>
                        <p className="text-sm text-gray-500 mt-0.5">
                            {isLoading ? 'Loading...' : `${summaryData?.length || 0} recordings found`}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-gray-100 rounded-full transition-colors text-gray-500"
                    >
                        <X className="w-6 h-6" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6 bg-gray-50">
                    {isLoading && (
                        <div className="flex items-center justify-center h-full">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                        </div>
                    )}

                    {error && (
                        <div className="flex items-center justify-center h-full text-red-600">
                            Failed to load data: {error.message}
                        </div>
                    )}

                    {!isLoading && !error && (!summaryData || summaryData.length === 0) && (
                        <div className="flex flex-col items-center justify-center h-full text-gray-500">
                            <Tag className="w-12 h-12 mb-3 text-gray-300" />
                            <p>No recordings found for this selection</p>
                        </div>
                    )}

                    {!isLoading && !error && summaryData?.length > 0 && (
                        <div className="grid gap-4">
                            {summaryData.map((item) => (
                                <div key={item.id} className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-shadow flex gap-4">
                                    {/* Thumbnail Section */}
                                    <div className="w-40 h-24 bg-gray-100 rounded-md overflow-hidden flex-shrink-0 relative border border-gray-200">
                                        <FileThumbnail
                                            fileId={item.file_id}
                                            className="w-full h-full object-cover"
                                        />

                                        {/* Duration Badge */}
                                        {item.duration && (
                                            <div className="absolute bottom-1 right-1 bg-black bg-opacity-75 text-white text-[10px] px-1.5 py-0.5 rounded font-medium z-10">
                                                {item.duration}
                                            </div>
                                        )}
                                    </div>

                                    {/* Content Section */}
                                    <div className="flex-1 min-w-0 flex flex-col justify-between">
                                        <div>
                                            <div className="flex justify-between items-start mb-1">
                                                <h3 className="font-semibold text-gray-900 line-clamp-1 text-lg" title={item.title || item.filename}>
                                                    {item.title || item.filename}
                                                </h3>
                                                <div className="flex items-center gap-2">
                                                    {item.session_id && (
                                                        <button
                                                            onClick={(e) => handleOpenFolder(e, item.session_id)}
                                                            className="p-1 hover:bg-gray-100 rounded transition-colors group"
                                                            title="Open in Finder"
                                                        >
                                                            <FolderOpen className="w-4 h-4 text-gray-400 group-hover:text-blue-600" />
                                                        </button>
                                                    )}
                                                    <span className={`px-2 py-0.5 rounded text-xs font-medium uppercase tracking-wide shrink-0 ${item.state === 'COMPLETED' ? 'bg-green-100 text-green-700' :
                                                        item.state === 'FAILED' ? 'bg-red-100 text-red-700' :
                                                            'bg-blue-100 text-blue-700'
                                                        } `}>
                                                        {item.state}
                                                    </span>
                                                </div>
                                            </div>

                                            <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm text-gray-600 mt-1">
                                                <div className="flex items-center gap-1.5">
                                                    <Calendar className="w-3.5 h-3.5 text-gray-400" />
                                                    <span>
                                                        {(() => {
                                                            if (item.recording_date) return new Date(item.recording_date).toLocaleDateString();
                                                            // Try parsing YYYY-MM-DD from filename
                                                            const match = item.filename?.match(/(\d{4}-\d{2}-\d{2})/);
                                                            if (match) return new Date(match[1]).toLocaleDateString();
                                                            return new Date(item.created_at).toLocaleDateString();
                                                        })()}
                                                    </span>
                                                </div>
                                                {item.faculty && (
                                                    <div className="flex items-center gap-1.5">
                                                        <Users className="w-3.5 h-3.5 text-gray-400" />
                                                        <span className="truncate">{item.faculty}</span>
                                                    </div>
                                                )}
                                                {item.content_type && (
                                                    <div className="flex items-center gap-1.5">
                                                        <Tag className="w-3.5 h-3.5 text-gray-400" />
                                                        <span className="truncate">{item.content_type}</span>
                                                    </div>
                                                )}
                                            </div>
                                        </div>

                                        {(item.speaker || item.audience) && (
                                            <div className="mt-2 flex flex-wrap gap-2">
                                                {item.speaker && (
                                                    <span className="inline-flex items-center px-2 py-1 rounded bg-gray-50 text-xs text-gray-600 border border-gray-100">
                                                        <User className="w-3 h-3 mr-1.5 text-gray-400" />
                                                        {item.speaker}
                                                    </span>
                                                )}
                                                {item.audience && (
                                                    <span className="inline-flex items-center px-2 py-1 rounded bg-gray-50 text-xs text-gray-600 border border-gray-100">
                                                        <Users className="w-3 h-3 mr-1.5 text-gray-400" />
                                                        {item.audience}
                                                    </span>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}