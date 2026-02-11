import React from 'react';
import { FolderOpen, MapPin } from 'lucide-react';
import { FileThumbnail } from './FileThumbnail';
import { formatDateTime, getRelativeTimeFromDateTime } from '../utils/dateUtils';

/**
 * SessionGridCard Component
 * 
 * A compact card for grid view display showing:
 * - Thumbnail
 * - Session name and date
 * - Analytics metadata (Title, Description, Faculty, Content Type, Audience, Speakers)
 * - Open Folder button
 * 
 * This card does NOT expand or show pipeline data.
 */
export function SessionGridCard({
    session,
    analyticsData = [],
    selectMode,
    index,
    sessionIds = []
}) {
    // Find the program file for thumbnail
    const programFile = session.files?.find(f => f.is_program_output) || 
        (session.primary_file_id ? {
            id: session.primary_file_id,
            is_empty: session.primary_is_empty,
            etag: session.primary_file_etag
        } : null);

    // Get analytics data for the program file
    const programAnalytics = programFile && analyticsData.length > 0
        ? analyticsData.find(a => a.file_id === programFile.id)
        : (programFile?.analytics || null);

    const handleOpenFolder = async (e) => {
        e.stopPropagation();
        try {
            const resp = await fetch(`/api/sessions/${session.id}/open-folder`, { method: 'POST' });
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
            className={`relative border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm hover:shadow-md transition-shadow ${
                selectMode?.isSelected(session.id) ? 'ring-2 ring-blue-500' : ''
            }`}
            onClick={(e) => {
                if (selectMode?.isSelectMode) {
                    if (e.shiftKey && sessionIds.length > 0) {
                        selectMode.handleShiftClick(session.id, sessionIds, index);
                    } else {
                        selectMode.handleRegularClick(session.id, index);
                    }
                }
            }}
        >
            {/* Selection Overlay */}
            {selectMode?.isSelectMode && (
                <div className="absolute top-3 left-3 z-10">
                    <div className={`w-5 h-5 rounded border flex items-center justify-center transition-colors ${
                        selectMode.isSelected(session.id) 
                            ? 'bg-blue-600 border-blue-600' 
                            : 'bg-white border-gray-300'
                    }`}>
                        {selectMode.isSelected(session.id) && (
                            <div className="w-2.5 h-2.5 bg-white rounded-sm" />
                        )}
                    </div>
                </div>
            )}

            {/* Thumbnail */}
            <div className="relative">
                {programFile ? (
                    <FileThumbnail 
                        fileId={programFile.id} 
                        isEmpty={programFile.is_empty} 
                        className="w-full" 
                        etag={programFile.etag} 
                    />
                ) : (
                    <div 
                        className="w-full bg-gray-200 flex items-center justify-center" 
                        style={{ aspectRatio: '16/9' }}
                    >
                        <span className="text-gray-500 text-xs">No thumbnail</span>
                    </div>
                )}

            </div>

            {/* Content */}
            <div className="p-3">
                {/* Session Header */}
                <div className="mb-2">
                    <div className="flex items-start justify-between gap-2">
                        <h3 className="font-semibold text-gray-800 text-sm leading-tight line-clamp-1" title={session.name}>
                            {session.name}
                        </h3>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                        <span className="text-xs text-gray-500" title={formatDateTime(session.recording_date, session.recording_time, 'en-AU')}>
                            {getRelativeTimeFromDateTime(session.recording_date, session.recording_time)}
                        </span>
                        <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-500">
                            <MapPin className="w-2.5 h-2.5" />
                            {session.campus || 'Keysborough'}
                        </span>
                        <button
                            onClick={handleOpenFolder}
                            className="p-0.5 hover:bg-gray-100 rounded transition-colors group"
                            title="Open in Finder"
                        >
                            <FolderOpen className="w-3.5 h-3.5 text-gray-400 group-hover:text-blue-600" />
                        </button>
                    </div>
                </div>

                {/* Analytics Data */}
                {programAnalytics ? (
                    <div className="space-y-2">
                        {/* Title */}
                        {programAnalytics.title && (
                            <div>
                                <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Title</div>
                                <div className="text-xs text-gray-800 font-medium line-clamp-2" title={programAnalytics.title}>
                                    {programAnalytics.title}
                                </div>
                            </div>
                        )}

                        {/* Description */}
                        {programAnalytics.description && (
                            <div>
                                <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Description</div>
                                <div className="text-xs text-gray-600 line-clamp-2" title={programAnalytics.description}>
                                    {programAnalytics.description}
                                </div>
                            </div>
                        )}

                        {/* Badges Row */}
                        <div className="flex flex-wrap gap-1">
                            {/* Faculty */}
                            {programAnalytics.faculty && (
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-100 text-purple-700">
                                    {programAnalytics.faculty === 'N/A' ? 'Whole School' : programAnalytics.faculty}
                                </span>
                            )}

                            {/* Content Type */}
                            {programAnalytics.content_type && (
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-100 text-indigo-700">
                                    {programAnalytics.content_type}
                                </span>
                            )}

                            {/* Audience */}
                            {(programAnalytics.audience || programAnalytics.audience_type) && (
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-700">
                                    {programAnalytics.audience || 
                                        (programAnalytics.audience_type && 
                                            (() => {
                                                try {
                                                    return JSON.parse(programAnalytics.audience_type).join(', ');
                                                } catch {
                                                    return programAnalytics.audience_type;
                                                }
                                            })()
                                        ) || '-'}
                                </span>
                            )}

                            {/* Speakers */}
                            {(programAnalytics.speaker || programAnalytics.speaker_type) && (
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700">
                                    {programAnalytics.speaker || 
                                        (programAnalytics.speaker_type && 
                                            (() => {
                                                try {
                                                    return JSON.parse(programAnalytics.speaker_type).join(', ');
                                                } catch {
                                                    return programAnalytics.speaker_type;
                                                }
                                            })()
                                        ) || '-'}
                                </span>
                            )}
                        </div>
                    </div>
                ) : (
                    <div className="text-xs text-gray-400 italic py-2">
                        No analytics data available
                    </div>
                )}
            </div>
        </div>
    );
}
