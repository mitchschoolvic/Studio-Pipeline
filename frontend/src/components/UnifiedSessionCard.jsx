import React, { useState, useEffect, useRef } from 'react';
import { ChevronRight, FolderOpen, Mic, RefreshCw, AlertTriangle, FileText, Play, Pause, CheckCircle, XCircle, Loader2, Circle, Slash, Code, Brain, Trash2, Clock, X, MapPin } from 'lucide-react';
import { FileThumbnail } from './FileThumbnail';
import { BitrateBadge } from './BitrateBadge';
import { formatDateTime, getRelativeTimeFromDateTime } from '../utils/dateUtils';

import { useSessions } from '../contexts/SessionsContext';

/**
 * UnifiedSessionCard Component
 * 
 * Merges functionality from PipelineSessionCard and SessionCard (Analytics).
 * Displays session details with different content based on 'mode'.
 * 
 * @param {Object} session - The session data
 * @param {string} mode - 'pipeline' | 'analytics'
 * @param {boolean} isExpanded - Whether the card is expanded
 * @param {function} onToggleExpand - Toggle expand handler
 * @param {Object} selectMode - Selection mode state
 * @param {function} onFilesLoaded - Callback when files are loaded
 * @param {function} handleReprocessSession - Handler for reprocessing (analytics mode)
 * @param {function} setSelectedTranscript - Handler for showing transcript (analytics mode)
 */
export function UnifiedSessionCard({
    session,
    mode = 'pipeline',
    isExpanded,
    onToggleExpand,
    selectMode,
    onFilesLoaded,
    handleReprocessSession,
    setSelectedTranscript,
    setSelectedRawOutput,
    analyticsData,
    index,
    sessionIds = []
}) {
    const cardRef = useRef(null);
    const { ensureSessionFiles, getFiles } = useSessions();
    const [bitrateThreshold, setBitrateThreshold] = useState(500);
    const [localFiles, setLocalFiles] = useState([]); // fallback when store isn't ready yet
    const [loading, setLoading] = useState(false);
    const [showEmptyFiles, setShowEmptyFiles] = useState(false);
    const fetchAttemptedRef = useRef(new Set());

    // Get files from store or local fallback
    const storeFiles = getFiles(session.id);
    const files = storeFiles.length > 0 ? storeFiles : localFiles;

    // Ensure files loaded when expanded
    useEffect(() => {
        if (!isExpanded) return;
        if (fetchAttemptedRef.current.has(session.id)) return;
        if (files.length > 0) return;

        fetchAttemptedRef.current.add(session.id);
        let cancelled = false;

        const loadFiles = async () => {
            setLoading(true);
            try {
                const fetchedFiles = await ensureSessionFiles(session.id);
                if (!cancelled && fetchedFiles && fetchedFiles.length > 0) {
                    if (getFiles(session.id).length === 0) {
                        setLocalFiles(fetchedFiles);
                    }
                    onFilesLoaded?.();
                }
            } catch (error) {
                console.error('Failed to load files:', error);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };

        loadFiles();
        return () => { cancelled = true; };
    }, [isExpanded, session.id, ensureSessionFiles, getFiles, onFilesLoaded, files.length]);

    // Bitrate threshold
    useEffect(() => {
        (async () => {
            try {
                const res = await fetch('/api/settings');
                const settings = await res.json();
                const threshold = settings.find(s => s.key === 'bitrate_threshold_kbps');
                if (threshold) setBitrateThreshold(parseFloat(threshold.value));
            } catch { /* ignore */ }
        })();
    }, []);

    const programFile = files.find(f => f.is_program_output);
    const allIsoFiles = files.filter(f => f.is_iso);
    const isoFiles = allIsoFiles.filter(f => showEmptyFiles || !f.is_empty);

    // Construct display object for header
    const displayProgram = programFile || (session.primary_file_id ? {
        id: session.primary_file_id,
        is_empty: session.primary_is_empty,
        state: session.primary_file_state || 'DISCOVERED',
        filename: 'Program Output',
        size: 0
    } : null);

    // Helper functions
    const getProgressForFile = (file) => {
        if (!file) return 0;
        if (file.state === 'COMPLETED') return 100;
        if (file.jobs && file.jobs.length > 0) {
            const running = [...file.jobs].reverse().find(j => j.state === 'RUNNING');
            if (running && typeof running.progress_pct === 'number') return running.progress_pct;
            const latestJob = [...file.jobs].sort((a, b) => new Date(a.completed_at || a.started_at || a.created_at || 0) - new Date(b.completed_at || b.started_at || b.created_at || 0)).pop();
            if (latestJob && typeof latestJob.progress_pct === 'number') return latestJob.progress_pct;
        }
        const fallback = { DISCOVERED: 0, COPIED: 40, PROCESSING: 60, PROCESSED: 80, ORGANIZING: 90 };
        return fallback[file.state] || 0;
    };

    const getStateColor = (state) => ({
        DISCOVERED: 'text-blue-600 bg-blue-50', COPYING: 'text-yellow-600 bg-yellow-50', COPIED: 'text-green-600 bg-green-50', PROCESSING: 'text-orange-600 bg-orange-50', PROCESSED: 'text-green-600 bg-green-50', ORGANIZING: 'text-indigo-600 bg-indigo-50', COMPLETED: 'text-green-700 bg-green-100', FAILED: 'text-red-600 bg-red-50'
    }[state] || 'text-gray-600 bg-gray-50');

    const getStageLabel = (file) => {
        if (!file) return '';
        if (file.jobs && file.jobs.length) {
            const latest = file.jobs[file.jobs.length - 1];
            if (latest.progress_stage) return latest.progress_stage;
        }
        return ({ DISCOVERED: 'Pending', COPYING: 'Copying', COPIED: 'Copy Complete', PROCESSING: 'Audio Processing', PROCESSED: 'Processing Complete', ORGANIZING: 'Organizing Files', COMPLETED: 'Complete', FAILED: 'Failed' })[file.state] || file.state;
    };

    const formatBytes = (bytes = 0) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
    };

    const handleOpenFolder = async (e) => {
        e.stopPropagation();
        try {
            const resp = await fetch(`/api/sessions/${session.id}/open-folder`, { method: 'POST' });
            if (!resp.ok) { const err = await resp.json().catch(() => ({})); alert(`Failed to open folder: ${err.detail || 'Unknown error'}`); }
        } catch (err) { alert('Failed to open folder'); }
    };

    const programProgress = getProgressForFile(displayProgram);
    const completedFiles = files.filter(f => f.state === 'COMPLETED').length;
    const isoCompleted = allIsoFiles.filter(f => f.state === 'COMPLETED').length;

    // Analytics specific helpers
    const getAnalyticsStatus = (file) => {
        if (!file) return null;
        // Check if analytics data is passed as prop
        if (analyticsData && analyticsData.length > 0) {
            return analyticsData.find(a => a.file_id === file.id);
        }
        return file.analytics || null;
    };

    const programAnalytics = getAnalyticsStatus(programFile);

    // FTP Deletion status - check if any file in session is marked for deletion
    const markedFiles = files.filter(f => f.marked_for_deletion_at && !f.deleted_at);
    const isMarkedForDeletion = markedFiles.length > 0;
    const deletedFiles = files.filter(f => f.deleted_at);
    const isDeleted = deletedFiles.length > 0 && deletedFiles.length === files.length;

    // Get earliest marked date for display
    const earliestMarkedDate = markedFiles.length > 0
        ? markedFiles.reduce((earliest, f) => {
            const date = new Date(f.marked_for_deletion_at);
            return earliest ? (date < earliest ? date : earliest) : date;
        }, null)
        : null;

    // Calculate days until deletion (7 days from marked date)
    const getDaysUntilDeletion = () => {
        if (!earliestMarkedDate) return null;
        const sevenDaysLater = new Date(earliestMarkedDate);
        sevenDaysLater.setDate(sevenDaysLater.getDate() + 7);
        const now = new Date();
        const diffTime = sevenDaysLater - now;
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        return diffDays;
    };

    const daysUntilDeletion = getDaysUntilDeletion();

    // FTP Deletion handlers
    const handleMarkForDeletion = async (e) => {
        e.stopPropagation();
        if (!confirm(`Mark all files in "${session.name}" for FTP server deletion? They will be deleted after 7 days.`)) return;
        try {
            const res = await fetch(`/api/sessions/${session.id}/mark-for-deletion?mark=true`, { method: 'PUT' });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || 'Failed to mark for deletion');
            }
            // Refresh will happen via WebSocket
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    };

    const handleUnmarkForDeletion = async (e) => {
        e.stopPropagation();
        if (!confirm(`Unmark all files in "${session.name}" from FTP deletion?`)) return;
        try {
            const res = await fetch(`/api/sessions/${session.id}/mark-for-deletion?mark=false`, { method: 'PUT' });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || 'Failed to unmark');
            }
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    };

    const handleDeleteImmediately = async (e) => {
        e.stopPropagation();
        if (!confirm(`DELETE all files in "${session.name}" from FTP server IMMEDIATELY?\n\nThis cannot be undone!`)) return;
        try {
            const res = await fetch(`/api/sessions/${session.id}/delete-immediately`, { method: 'DELETE' });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || 'Failed to delete');
            }
            const result = await res.json();
            alert(`Deleted ${result.success_count} files from FTP server.${result.failure_count > 0 ? ` (${result.failure_count} failed)` : ''}`);
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    };

    return (
        <div ref={cardRef} className={`relative border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm transition-all ${selectMode?.isSelected(session.id) ? 'ring-2 ring-blue-500' : ''}`}>

            {/* Selection Overlay */}
            {selectMode?.isSelectMode && (
                <div
                    className="absolute inset-0 z-10 bg-white bg-opacity-0 cursor-pointer"
                    onClick={(e) => {
                        if (e.shiftKey && sessionIds?.length > 0) {
                            selectMode.handleShiftClick(session.id, sessionIds, index);
                        } else {
                            selectMode.handleRegularClick(session.id, index);
                        }
                    }}
                >
                    <div className="absolute top-4 left-4">
                        <div className={`w-5 h-5 rounded border flex items-center justify-center transition-colors ${selectMode.isSelected(session.id) ? 'bg-blue-600 border-blue-600' : 'bg-white border-gray-300'}`}>
                            {selectMode.isSelected(session.id) && <div className="w-2.5 h-2.5 bg-white rounded-sm" />}
                        </div>
                    </div>
                </div>
            )}

            {/* Header */}
            <div
                className="bg-gradient-to-r from-gray-50 to-white p-4 cursor-pointer hover:bg-gray-100 transition-colors"
                onClick={(e) => {
                    if (e.target.closest('button')) return;
                    if (selectMode?.isSelectMode) return;
                    onToggleExpand?.();
                }}
            >
                <div className="flex items-center justify-between">
                    <div className={`flex items-center gap-3 flex-1 ${selectMode?.isSelectMode ? 'pl-8' : ''}`}>
                        {/* Expand Arrow */}
                        <div className={`transform transition-transform ${isExpanded ? 'rotate-90' : ''}`}>
                            <ChevronRight className="w-4 h-4 text-gray-500" />
                        </div>

                        {/* Thumbnail */}
                        <div className="w-64">
                            {displayProgram ? (
                                <FileThumbnail fileId={displayProgram.id} isEmpty={displayProgram.is_empty} className="w-64 rounded overflow-hidden shadow-sm" etag={displayProgram.etag} />
                            ) : (
                                <div className="w-64 rounded overflow-hidden bg-purple-200 border border-purple-400 flex items-center justify-center" style={{ aspectRatio: '16/9' }}>
                                    {loading ? (
                                        <div className="animate-pulse text-purple-800 text-[11px] font-medium">Loading...</div>
                                    ) : (
                                        <div className="text-purple-800 text-[11px] font-medium">No file</div>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Session Info */}
                        <div className="flex-1">
                            <div className="flex items-center gap-3">
                                <h3 className="font-semibold text-gray-800">{session.name}</h3>
                                <span className="text-sm text-gray-500" title={formatDateTime(session.recording_date, session.recording_time, 'en-AU')}>
                                    {getRelativeTimeFromDateTime(session.recording_date, session.recording_time)}
                                </span>

                                {/* Campus Badge */}
                                <span className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200">
                                    <MapPin className="w-3 h-3" />
                                    {session.campus || 'Keysborough'}
                                </span>

                                {/* FTP Deletion Badge */}
                                {isDeleted ? (
                                    <span className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
                                        <Trash2 className="w-3 h-3" />
                                        Deleted from FTP
                                    </span>
                                ) : isMarkedForDeletion && (
                                    <span className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700 animate-pulse">
                                        <Clock className="w-3 h-3" />
                                        Marked for deletion {daysUntilDeletion !== null && daysUntilDeletion > 0 ? `(${daysUntilDeletion}d)` : '(soon)'}
                                    </span>
                                )}
                            </div>

                            <div className="flex items-center gap-4 mt-1">
                                {displayProgram && (
                                    <span className={`text-xs font-medium px-2 py-0.5 rounded ${getStateColor(displayProgram.state)}`}>
                                        {getStageLabel(displayProgram)}
                                    </span>
                                )}
                                <span className="text-xs text-gray-600">{files.length} files</span>
                                {mode === 'pipeline' && allIsoFiles.length > 0 && (
                                    <span className="text-xs text-gray-600">ISO: {isoCompleted}/{allIsoFiles.length} copied</span>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Right Side Stats/Actions */}
                    <div className="flex items-center gap-4">
                        {/* FTP Deletion Actions */}
                        {!isDeleted && mode === 'pipeline' && (
                            <div className="flex items-center gap-1">
                                {isMarkedForDeletion ? (
                                    <>
                                        <button
                                            onClick={handleUnmarkForDeletion}
                                            className="p-2 hover:bg-green-100 rounded-lg transition-colors group"
                                            title="Cancel FTP deletion"
                                        >
                                            <X className="w-4 h-4 text-gray-500 group-hover:text-green-600" />
                                        </button>
                                        <button
                                            onClick={handleDeleteImmediately}
                                            className="p-2 hover:bg-red-100 rounded-lg transition-colors group"
                                            title="Delete from FTP now"
                                        >
                                            <Trash2 className="w-4 h-4 text-red-500 group-hover:text-red-700" />
                                        </button>
                                    </>
                                ) : (
                                    <button
                                        onClick={handleMarkForDeletion}
                                        className="p-2 hover:bg-red-100 rounded-lg transition-colors group"
                                        title="Mark for FTP deletion"
                                    >
                                        <Clock className="w-4 h-4 text-gray-400 group-hover:text-red-600" />
                                    </button>
                                )}
                            </div>
                        )}

                        {completedFiles > 0 && (
                            <button onClick={handleOpenFolder} className="p-2 hover:bg-gray-200 rounded-lg transition-colors group" title="Open in Finder">
                                <FolderOpen className="w-5 h-5 text-gray-600 group-hover:text-blue-600" />
                            </button>
                        )}

                        <div className="text-right">
                            <div className="text-sm font-medium text-gray-700">{formatBytes(session.total_size)}</div>
                            <div className="text-xs text-gray-500">{session.file_count} files</div>
                        </div>

                        {/* Progress Bar (Pipeline Mode) or Status (Analytics Mode) */}
                        {mode === 'pipeline' ? (
                            <div className="w-32">
                                {displayProgram ? (
                                    <div className="flex items-center gap-2">
                                        <div className="flex-1 bg-gray-200 rounded-full h-2">
                                            <div className={`h-2 rounded-full transition-all duration-300 ${displayProgram.state === 'COMPLETED' ? 'bg-green-500' : displayProgram.state === 'FAILED' ? 'bg-red-500' : 'bg-blue-500'}`} style={{ width: `${programProgress}%` }} />
                                        </div>
                                        <span className="text-xs text-gray-600 font-medium w-10 text-right">{Math.round(programProgress)}%</span>
                                    </div>
                                ) : (
                                    <div className="flex items-center gap-2">
                                        <div className="flex-1 bg-gray-200 rounded-full h-2 overflow-hidden">
                                            <div className="h-2 bg-gray-300 animate-pulse" style={{ width: '35%' }} />
                                        </div>
                                        <span className="text-xs text-gray-400 font-medium w-10 text-right">--</span>
                                    </div>
                                )}
                            </div>
                        ) : (
                            // Analytics Mode Status
                            <div className="w-32 flex justify-end">
                                {/* Placeholder for analytics status summary if needed in collapsed state */}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Expanded Content */}
            {isExpanded && (
                <div className="border-t border-gray-200 bg-gray-50">
                    {/* Program File Details */}
                    {programFile && (
                        <div className="p-4 border-b border-gray-200 bg-white">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">

                                    <div>
                                        <div className="font-medium text-gray-800">Program Output</div>
                                        <div className="text-xs text-gray-500">{programFile.filename} • {formatBytes(programFile.size)} {programFile.is_empty && <span className="ml-2 text-yellow-600">(Empty)</span>}</div>

                                        {/* Analytics Actions */}
                                        {mode === 'analytics' && (
                                            <div className="flex items-center gap-2 mt-2">
                                                {programAnalytics?.transcript ? (
                                                    <button
                                                        onClick={(e) => { e.stopPropagation(); setSelectedTranscript(programAnalytics); }}
                                                        className="flex items-center gap-1.5 px-2 py-1 bg-blue-50 text-blue-700 rounded hover:bg-blue-100 text-xs font-medium transition-colors"
                                                    >
                                                        <FileText className="w-3 h-3" />
                                                        View Transcript
                                                    </button>
                                                ) : (
                                                    <span className="text-xs text-gray-400 italic">No transcript available</span>
                                                )}

                                                {programAnalytics?.analysis_json && (
                                                    <button
                                                        onClick={(e) => { e.stopPropagation(); setSelectedRawOutput(programAnalytics); }}
                                                        className="flex items-center gap-1.5 px-2 py-1 bg-purple-50 text-purple-700 rounded hover:bg-purple-100 text-xs font-medium transition-colors"
                                                        title="View Raw LLM Output"
                                                    >
                                                        <Code className="w-3 h-3" />
                                                        Raw Output
                                                    </button>
                                                )}

                                                <div className="flex flex-col gap-1">
                                                    <button
                                                        onClick={async (e) => {
                                                            e.stopPropagation();
                                                            if (!confirm('Reprocess Transcript? This will clear existing analysis.')) return;
                                                            try {
                                                                const res = await fetch(`/api/analytics/${programFile.id}/re-transcribe`, { method: 'POST' });
                                                                if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
                                                                alert('Transcription queued');
                                                            } catch (err) {
                                                                alert(`Error: ${err.message}`);
                                                            }
                                                        }}
                                                        className="flex items-center gap-1.5 px-2 py-1 bg-orange-50 text-orange-700 rounded hover:bg-orange-100 text-xs font-medium transition-colors"
                                                        title="Redo Step 1: Transcribe Audio"
                                                    >
                                                        <RefreshCw className="w-3 h-3" />
                                                        Reprocess Transcript
                                                    </button>

                                                    <button
                                                        onClick={async (e) => {
                                                            e.stopPropagation();
                                                            if (!confirm('Reprocess Analytics? This will re-run LLM analysis.')) return;
                                                            try {
                                                                const res = await fetch(`/api/analytics/${programFile.id}/analyze`, { method: 'POST' });
                                                                if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
                                                                alert('Analysis queued');
                                                            } catch (err) {
                                                                alert(`Error: ${err.message}`);
                                                            }
                                                        }}
                                                        className="flex items-center gap-1.5 px-2 py-1 bg-indigo-50 text-indigo-700 rounded hover:bg-indigo-100 text-xs font-medium transition-colors"
                                                        title="Redo Step 2: Run LLM Analysis"
                                                    >
                                                        <Brain className="w-3 h-3" />
                                                        Reprocess Analytics
                                                    </button>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <div className="flex items-center gap-4">
                                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStateColor(programFile.state)}`}>{getStageLabel(programFile)}</span>

                                    {mode === 'pipeline' && (
                                        <div className="w-32">
                                            <div className="flex items-center gap-2">
                                                <div className="flex-1 bg-gray-200 rounded-full h-1.5">
                                                    <div className={`h-1.5 rounded-full transition-all duration-300 ${programFile.state === 'COMPLETED' ? 'bg-green-500' : programFile.state === 'FAILED' ? 'bg-red-500' : 'bg-blue-500'}`} style={{ width: `${programProgress}%` }} />
                                                </div>
                                                <span className="text-xs text-gray-600 font-medium w-10 text-right">{Math.round(programProgress)}%</span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Analytics Metadata Display */}
                            {mode === 'analytics' && programAnalytics && (
                                <div className="mt-4 pt-3 border-t border-gray-100">
                                    <div className="grid grid-cols-2 gap-y-3 gap-x-6">
                                        <div className="col-span-2">
                                            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Title</div>
                                            <div className="text-sm font-medium text-gray-900">{programAnalytics.title || <span className="text-gray-400 italic">No title generated</span>}</div>
                                        </div>

                                        <div className="col-span-2">
                                            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Description</div>
                                            <div className="text-sm text-gray-700 line-clamp-2" title={programAnalytics.description}>{programAnalytics.description || <span className="text-gray-400 italic">No description available</span>}</div>
                                        </div>

                                        <div>
                                            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Faculty</div>
                                            {programAnalytics.faculty ? (
                                                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
                                                    {programAnalytics.faculty}
                                                </span>
                                            ) : <span className="text-sm text-gray-400">-</span>}
                                        </div>

                                        <div>
                                            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Content Type</div>
                                            {programAnalytics.content_type ? (
                                                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-800">
                                                    {programAnalytics.content_type}
                                                </span>
                                            ) : <span className="text-sm text-gray-400">-</span>}
                                        </div>

                                        <div>
                                            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Audience</div>
                                            {programAnalytics.audience || programAnalytics.audience_type ? (
                                                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                                                    {programAnalytics.audience || (programAnalytics.audience_type && JSON.parse(programAnalytics.audience_type).join(', ')) || '-'}
                                                </span>
                                            ) : <span className="text-sm text-gray-400">-</span>}
                                        </div>

                                        <div>
                                            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Speakers</div>
                                            {programAnalytics.speaker || programAnalytics.speaker_type ? (
                                                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                                                    {programAnalytics.speaker || (programAnalytics.speaker_type && JSON.parse(programAnalytics.speaker_type).join(', ')) || '-'}
                                                </span>
                                            ) : <span className="text-sm text-gray-400">-</span>}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Pipeline Process Status History (Pipeline Mode) */}
                    {mode === 'pipeline' && programFile && (
                        <div className="px-4 pb-4">
                            <div className="mt-4 pt-4 border-t border-gray-100">
                                <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Pipeline Status</div>
                                <div className="flex items-center justify-between relative">
                                    {/* Connecting Line */}
                                    <div className="absolute top-3 left-0 w-full h-0.5 bg-gray-100 -z-10" />

                                    {(() => {
                                        const steps = [
                                            { id: 'copy', label: 'Ingest', status: 'waiting' },
                                            { id: 'process', label: 'Process', status: 'waiting' },
                                            { id: 'organize', label: 'Organize', status: 'waiting' },
                                            { id: 'transcribe', label: 'Transcribe', status: 'waiting' },
                                            { id: 'analyze', label: 'Analyze', status: 'waiting' }
                                        ];

                                        const f = programFile;
                                        const a = programAnalytics;

                                        // 1. Ingest
                                        if (['COPIED', 'PROCESSING', 'PROCESSED', 'ORGANIZING', 'COMPLETED'].includes(f.state)) steps[0].status = 'completed';
                                        else if (f.state === 'COPYING') steps[0].status = 'running';
                                        else if (f.state === 'FAILED') steps[0].status = 'failed';

                                        // 2. Process
                                        if (['PROCESSED', 'ORGANIZING', 'COMPLETED'].includes(f.state)) steps[1].status = 'completed';
                                        else if (f.state === 'PROCESSING') steps[1].status = 'running';
                                        else if (f.state === 'FAILED' && steps[0].status === 'completed') steps[1].status = 'failed';

                                        // 3. Organize
                                        if (['COMPLETED'].includes(f.state)) steps[2].status = 'completed';
                                        else if (f.state === 'ORGANIZING') steps[2].status = 'running';
                                        else if (f.state === 'FAILED' && steps[1].status === 'completed') steps[2].status = 'failed';

                                        // 4. Transcribe
                                        if (a) {
                                            if (['TRANSCRIBED', 'ANALYZING', 'COMPLETED'].includes(a.state)) steps[3].status = 'completed';
                                            else if (a.state === 'TRANSCRIBING') steps[3].status = 'running';
                                            else if (a.state === 'FAILED') steps[3].status = 'failed';
                                            else if (a.state === 'SKIPPED') steps[3].status = 'disabled';
                                        } else if (f.state === 'COMPLETED') {
                                            steps[3].status = 'disabled';
                                        }

                                        // 5. Analyze
                                        if (a) {
                                            if (['COMPLETED'].includes(a.state)) steps[4].status = 'completed';
                                            else if (a.state === 'ANALYZING') steps[4].status = 'running';
                                            else if (a.state === 'FAILED' && steps[3].status === 'completed') steps[4].status = 'failed';
                                            else if (a.state === 'SKIPPED') steps[4].status = 'disabled';
                                        } else if (f.state === 'COMPLETED') {
                                            steps[4].status = 'disabled';
                                        }

                                        return steps.map((step, idx) => {
                                            let Icon = Circle;
                                            let colorClass = 'text-gray-300 bg-white';
                                            let labelClass = 'text-gray-400';

                                            if (step.status === 'completed') {
                                                Icon = CheckCircle;
                                                colorClass = 'text-green-600 bg-white';
                                                labelClass = 'text-green-700 font-medium';
                                            } else if (step.status === 'running') {
                                                Icon = Loader2;
                                                colorClass = 'text-blue-600 bg-white animate-spin';
                                                labelClass = 'text-blue-700 font-medium';
                                            } else if (step.status === 'failed') {
                                                Icon = XCircle;
                                                colorClass = 'text-red-600 bg-white';
                                                labelClass = 'text-red-700 font-medium';
                                            } else if (step.status === 'disabled') {
                                                Icon = Slash;
                                                colorClass = 'text-gray-300 bg-white';
                                                labelClass = 'text-gray-400 italic';
                                            }

                                            return (
                                                <div key={step.id} className="flex flex-col items-center z-0">
                                                    <div className={`w-6 h-6 rounded-full flex items-center justify-center ${step.status === 'running' ? '' : 'bg-white'}`}>
                                                        <Icon className={`w-5 h-5 ${colorClass}`} />
                                                    </div>
                                                    <span className={`text-[10px] mt-1 ${labelClass}`}>{step.label}</span>
                                                </div>
                                            );
                                        });
                                    })()}
                                </div>

                                {/* Detailed Processing Sub-steps */}
                                {(() => {
                                    const f = programFile;
                                    // Show details if in PROCESSING state or if PROCESSED/COMPLETED (history)
                                    // But mainly useful during PROCESSING to show progress
                                    if (!['PROCESSING', 'PROCESSED', 'ORGANIZING', 'COMPLETED'].includes(f.state)) return null;

                                    const subSteps = [
                                        { id: 'extract', label: 'Extract Audio' },
                                        { id: 'boost', label: 'Boost Levels' },
                                        { id: 'denoise', label: 'Denoise (AI)' },
                                        { id: 'mp3export', label: 'Export MP3' },
                                        { id: 'convert', label: 'Convert AAC' },
                                        { id: 'remux', label: 'Remux Video' },
                                        { id: 'quadsplit', label: 'Quad Split', optional: true }
                                    ];

                                    // Determine current sub-step index
                                    let currentSubStepIndex = -1;
                                    if (f.state === 'PROCESSING' && f.processing_stage) {
                                        currentSubStepIndex = subSteps.findIndex(s => s.id === f.processing_stage);
                                    } else if (['PROCESSED', 'ORGANIZING', 'COMPLETED'].includes(f.state)) {
                                        currentSubStepIndex = subSteps.length; // All completed (except optional)
                                    }

                                    return (
                                        <div className="mt-4 bg-gray-50 rounded-md p-3 border border-gray-100">
                                            <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Processing Details</div>
                                            <div className="grid grid-cols-7 gap-1">
                                                {subSteps.map((step, idx) => {
                                                    let status = 'waiting';
                                                    if (currentSubStepIndex > idx) status = 'completed';
                                                    else if (currentSubStepIndex === idx) status = 'running';

                                                    // Handle optional steps (Quad Split)
                                                    if (step.optional) {
                                                        // Only show as running/completed if explicitly active
                                                        if (f.processing_stage === step.id) status = 'running';
                                                        else if (status === 'completed' && f.processing_stage !== step.id) status = 'disabled'; // Assume skipped if passed
                                                        else status = 'disabled';
                                                    }

                                                    let barColor = 'bg-gray-200';
                                                    let textColor = 'text-gray-400';

                                                    if (status === 'completed') {
                                                        barColor = 'bg-green-500';
                                                        textColor = 'text-green-700';
                                                    } else if (status === 'running') {
                                                        barColor = 'bg-blue-500 animate-pulse';
                                                        textColor = 'text-blue-700 font-medium';
                                                    } else if (status === 'disabled') {
                                                        barColor = 'bg-gray-100';
                                                        textColor = 'text-gray-300';
                                                    }

                                                    return (
                                                        <div key={step.id} className="flex flex-col gap-1">
                                                            <div className={`h-1 w-full rounded-full ${barColor}`} />
                                                            <span className={`text-[9px] truncate ${textColor}`} title={step.label}>{step.label}</span>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                            {f.state === 'PROCESSING' && f.processing_detail && (
                                                <div className="mt-2 text-xs text-blue-600 flex items-center gap-1.5">
                                                    <Loader2 className="w-3 h-3 animate-spin" />
                                                    {f.processing_detail}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })()}
                            </div>
                        </div>
                    )}

                    {/* ISO Files (Pipeline Mode Only) */}
                    {mode === 'pipeline' && allIsoFiles.length > 0 && (
                        <div className="p-4">
                            <div className="flex items-center justify-between mb-3">
                                <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide">ISO Camera Files (Copy Only)</div>
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <div className="relative inline-block w-8 h-4 align-middle select-none transition duration-200 ease-in">
                                        <input type="checkbox" name="toggle" id="toggle" className="toggle-checkbox absolute block w-4 h-4 rounded-full bg-white border-4 appearance-none cursor-pointer transition-transform duration-200 ease-in-out checked:translate-x-full checked:border-blue-600" checked={showEmptyFiles} onChange={(e) => setShowEmptyFiles(e.target.checked)} />
                                        <div className={`toggle-label block overflow-hidden h-4 rounded-full cursor-pointer ${showEmptyFiles ? 'bg-blue-600' : 'bg-gray-300'}`}></div>
                                    </div>
                                    <span className="text-xs text-gray-500">Show Empty Files</span>
                                </label>
                            </div>

                            {isoFiles.length === 0 && !showEmptyFiles ? (
                                <div className="text-xs text-gray-400 italic text-center py-4 border border-dashed border-gray-200 rounded">
                                    Empty files hidden. Toggle "Show Empty Files" to view.
                                </div>
                            ) : (
                                <div className="flex gap-3">
                                    {isoFiles.map((file, idx) => {
                                        const progress = getProgressForFile(file);
                                        const cameraMatch = file.filename?.match(/CAM\s+(\d+)/i);
                                        const cameraNum = cameraMatch ? cameraMatch[1] : idx + 1;
                                        return (
                                            <div key={file.id} className="flex-1 min-w-0 border border-gray-200 rounded p-2 bg-white hover:shadow-md transition-shadow">
                                                <FileThumbnail fileId={file.id} isEmpty={file.is_empty} className="w-full aspect-video rounded mb-2" etag={file.etag} />
                                                <div className="text-xs text-gray-700 font-medium mb-1 truncate">Camera {cameraNum}</div>
                                                <div className="text-xs text-gray-500 mb-2 flex items-center gap-1 flex-wrap">
                                                    <span>{formatBytes(file.size)}</span>
                                                    {file.is_empty && <span className="text-yellow-600">(Empty)</span>}
                                                </div>
                                                <div className="mb-2"><BitrateBadge fileSize={file.size} duration={file.duration} thresholdKbps={bitrateThreshold} /></div>
                                                <div className="flex items-center gap-1">
                                                    <div className="flex-1 bg-gray-200 rounded-full h-1">
                                                        <div className={`h-1 rounded-full transition-all duration-300 ${file.state === 'COMPLETED' ? 'bg-green-500' : file.state === 'FAILED' ? 'bg-red-500' : 'bg-blue-500'}`} style={{ width: `${progress}%` }} />
                                                    </div>
                                                    <span className="text-xs text-gray-500 w-8 text-right">{Math.round(progress)}%</span>
                                                </div>
                                                <div className={`text-xs mt-1 px-1.5 py-0.5 rounded text-center ${getStateColor(file.state)}`}>{file.state === 'COMPLETED' ? '✓' : getStageLabel(file)}</div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
