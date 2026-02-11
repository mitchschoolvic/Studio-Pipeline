import { useState, useEffect, useMemo } from 'react';
import { Play, Pause, Brain, Calendar } from 'lucide-react';
import { useWebSocket } from '../hooks/useWebSocket';
import { useSessions } from '../contexts/SessionsContext';
import { useSelectMode } from '../contexts/SelectModeContext';
import { SessionToolbar } from '../components/SessionToolbar';
import { SelectModeToolbar } from '../components/SelectModeToolbar';
import { UnifiedSessionCard } from '../components/UnifiedSessionCard';
import { SessionGridCard } from '../components/SessionGridCard';
import { AnalyticsSpreadsheetPreview } from '../components/AnalyticsSpreadsheetPreview';
import { AnalyticsView } from './AnalyticsView';
import { DevQueueView } from './DevQueueView';
import PauseConfirmDialog from '../components/PauseConfirmDialog';
import MaintenanceModal from '../components/MaintenanceModal';
import { SidePanel } from '../components/SidePanel';
import { useValidation } from '../hooks/useValidation';
import { useFTPStatus } from '../hooks/useFTPStatus';
import { sortSessions, SORT_OPTIONS } from '../utils/sessionFilters';
import { getSortPreference, setSortPreference } from '../utils/sortPreference';
import { StatusOverlay } from '../components/StatusOverlay';
import { useAiInfo } from '../api/settings';
import { useRef } from 'react';
import { WebSocketStatus } from '../components/WebSocketStatus';

// School Term definitions (start dates)
const TERMS = [
    { label: 'Term 1', month: 0, day: 27 }, // Jan 27
    { label: 'Term 2', month: 3, day: 19 }, // Apr 19
    { label: 'Term 3', month: 6, day: 12 }, // Jul 12
    { label: 'Term 4', month: 9, day: 4 },  // Oct 4
];

// Get the term for a given date
const getTermForDate = (date) => {
    if (!date) return null;
    const d = new Date(date);
    const year = d.getFullYear();
    
    // Find which term the date falls into
    for (let i = TERMS.length - 1; i >= 0; i--) {
        const termStart = new Date(year, TERMS[i].month, TERMS[i].day);
        if (d >= termStart) {
            return { year, term: i + 1, label: TERMS[i].label };
        }
    }
    
    // If before Term 1 of current year, it's Term 4 of previous year
    return { year: year - 1, term: 4, label: 'Term 4' };
};

// Get all available year-term combinations from sessions
const getAvailableTerms = (sessions) => {
    const termSet = new Map();
    
    sessions.forEach(session => {
        if (session.recording_date) {
            const termInfo = getTermForDate(session.recording_date);
            if (termInfo) {
                const key = `${termInfo.year}-${termInfo.term}`;
                if (!termSet.has(key)) {
                    termSet.set(key, {
                        key,
                        year: termInfo.year,
                        term: termInfo.term,
                        label: `${termInfo.year} - ${termInfo.label}`,
                        count: 0
                    });
                }
                termSet.get(key).count++;
            }
        }
    });
    
    // Sort by year desc, then term desc
    return Array.from(termSet.values()).sort((a, b) => {
        if (a.year !== b.year) return b.year - a.year;
        return b.term - a.term;
    });
};

export function PipelineView({ onOpenSettings }) {
    const { connected, lastMessage } = useWebSocket();
    const { sessions, loading, fetchSessions } = useSessions();
    const selectMode = useSelectMode();

    const { validationStatus } = useValidation();
    const { ftpConnectionState, ftpHost, ftpPort, ftpErrorMessage } = useFTPStatus(validationStatus);
    
    // Check if AI features are available (returns { enabled: true/false } or null)
    const { data: aiInfo } = useAiInfo();
    const aiEnabled = aiInfo?.enabled === true;

    const [mainView, setMainView] = useState('files'); // 'files' | 'spreadsheet'
    const [viewMode, setViewMode] = useState('pipeline'); // 'pipeline' | 'analytics'
    const [layoutView, setLayoutView] = useState('list'); // 'list' | 'grid'
    const [selectedTerm, setSelectedTerm] = useState(null); // null = 'All', or term key like '2025-1'
    const [isPaused, setIsPaused] = useState(false);
    const [showPauseDialog, setShowPauseDialog] = useState(false);
    const [activeJobs, setActiveJobs] = useState(null);

    const [expandedSessions, setExpandedSessions] = useState([]);
    const [searchTerm, setSearchTerm] = useState('');
    const [facultyFilter, setFacultyFilter] = useState(null); // null = 'All', or faculty name
    const [contentTypeFilter, setContentTypeFilter] = useState(null); // null = 'All', or content type

    // Initialize sort from preference
    const [sortOption, setSortOption] = useState(() => {
        const pref = getSortPreference();
        return pref.sortType || SORT_OPTIONS.NEWEST;
    });

    // Handle sort change with persistence
    const handleSortChange = (newSort) => {
        setSortOption(newSort);
        // We don't strictly need direction for the simple dropdown, 
        // but the util expects it. Defaulting to 'desc' or 'asc' based on type 
        // is handled inside the sort logic implicitly, but for persistence 
        // we can just save the type. The util handles the rest.
        setSortPreference(newSort, 'desc');
    };

    const [maintenanceMode, setMaintenanceMode] = useState(false);
    const [maintenanceIssues, setMaintenanceIssues] = useState([]);

    // Analytics State
    const [analyticsPaused, setAnalyticsPaused] = useState(true);
    const [queuedCount, setQueuedCount] = useState(0);
    const [runningJobId, setRunningJobId] = useState(null);
    const [runWhenIdle, setRunWhenIdle] = useState(true);
    const [selectedTranscript, setSelectedTranscript] = useState(null);
    const [selectedRawOutput, setSelectedRawOutput] = useState(null);
    const [analyticsData, setAnalyticsData] = useState([]);

    // Status Overlay State
    const [statusOverlay, setStatusOverlay] = useState({ visible: false, message: '', type: 'success' });
    const statusTimeoutRef = useRef(null);

    const showStatus = (message, type = 'success') => {
        if (statusTimeoutRef.current) clearTimeout(statusTimeoutRef.current);
        setStatusOverlay({ visible: true, message, type });
        statusTimeoutRef.current = setTimeout(() => {
            setStatusOverlay(prev => ({ ...prev, visible: false }));
        }, 2000); // Hide after 2 seconds
    };

    // Auto-expand first session with active processing
    useEffect(() => {
        if (sessions.length > 0 && expandedSessions.length === 0) {
            const firstActive = sessions.find(s =>
                s.files && s.files.some(f => f.state !== 'COMPLETED' && f.state !== 'FAILED')
            );
            if (firstActive) {
                setExpandedSessions([firstActive.id]);
            }
        }
    }, [sessions]);

    // Fetch analytics data for search and analytics view
    useEffect(() => {
        if (mainView === 'files') {
            const fetchAnalytics = async () => {
                try {
                    const response = await fetch('/api/analytics/?limit=10000');
                    if (response.ok) {
                        const data = await response.json();
                        setAnalyticsData(data);
                    }
                } catch (error) {
                    console.error('Failed to fetch analytics:', error);
                }
            };
            fetchAnalytics();

            // Set up polling for analytics updates
            const interval = setInterval(fetchAnalytics, 10000);
            return () => clearInterval(interval);
        }
    }, [mainView]);

    const [analyticsStartHour, setAnalyticsStartHour] = useState(20);
    const [analyticsEndHour, setAnalyticsEndHour] = useState(6);
    const [analyticsScheduleEnabled, setAnalyticsScheduleEnabled] = useState(true);

    // Handle pause settings
    useEffect(() => {
        const fetchPauseSettings = async () => {
            try {
                const [processingRes, analyticsRes, idleRes, startHourRes, endHourRes, scheduleEnabledRes] = await Promise.all([
                    fetch('/api/settings/pause_processing'),
                    fetch('/api/analytics/pause-status'),
                    fetch('/api/analytics/settings/run-when-idle'),
                    fetch('/api/settings/analytics_start_hour'),
                    fetch('/api/settings/analytics_end_hour'),
                    fetch('/api/settings/analytics_schedule_enabled')
                ]);

                if (processingRes.ok) {
                    const data = await processingRes.json();
                    setIsPaused(String(data.value) === 'true');
                }

                if (analyticsRes.ok) {
                    const data = await analyticsRes.json();
                    setAnalyticsPaused(data.paused);
                    setQueuedCount(data.queued_count);
                    setRunningJobId(data.running_job_id);
                }

                if (idleRes.ok) {
                    const data = await idleRes.json();
                    setRunWhenIdle(data.enabled);
                }

                if (startHourRes.ok) {
                    const data = await startHourRes.json();
                    setAnalyticsStartHour(parseInt(data.value) || 20);
                }

                if (endHourRes.ok) {
                    const data = await endHourRes.json();
                    setAnalyticsEndHour(parseInt(data.value) || 6);
                }

                if (scheduleEnabledRes.ok) {
                    const data = await scheduleEnabledRes.json();
                    setAnalyticsScheduleEnabled(String(data.value) === 'true');
                }
            } catch (err) {
                console.warn('Could not fetch settings:', err);
            }
        };
        fetchPauseSettings();
    }, [connected]);

    const handleUpdateAnalyticsSchedule = async (start, end) => {
        try {
            // Update local state immediately
            setAnalyticsStartHour(start);
            setAnalyticsEndHour(end);

            // Save to backend
            await Promise.all([
                fetch('/api/settings/analytics_start_hour', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: 'analytics_start_hour', value: String(start) })
                }),
                fetch('/api/settings/analytics_end_hour', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: 'analytics_end_hour', value: String(end) })
                })
            ]);
            showStatus('Schedule updated');
        } catch (err) {
            console.error('Error updating analytics schedule:', err);
            showStatus('Failed to update schedule', 'error');
        }
    };

    const toggleAnalyticsSchedule = async () => {
        try {
            const newValue = !analyticsScheduleEnabled;
            setAnalyticsScheduleEnabled(newValue);

            await fetch('/api/settings/analytics_schedule_enabled', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: 'analytics_schedule_enabled', value: String(newValue) })
            });
            showStatus(newValue ? 'Schedule enabled' : 'Schedule disabled');
        } catch (err) {
            console.error('Error toggling analytics schedule:', err);
            showStatus('Failed to update setting', 'error');
            setAnalyticsScheduleEnabled(!analyticsScheduleEnabled); // Revert on error
        }
    };

    // Handle WebSocket messages
    useEffect(() => {
        if (lastMessage?.type === 'pause_state_changed') {
            setIsPaused(lastMessage.paused === true);
        }
        // Add listeners for analytics status updates if needed
    }, [lastMessage]);

    // Check system status (Maintenance Mode)
    useEffect(() => {
        const checkSystemStatus = async () => {
            try {
                const response = await fetch('/api/system/status', { cache: 'no-store' });
                if (response.ok) {
                    const data = await response.json();
                    console.log('System Status:', data);
                    if (data.state === 'MAINTENANCE') {
                        setMaintenanceMode(true);
                        setMaintenanceIssues(data.schema_status?.issues || []);
                    } else {
                        setMaintenanceMode(false);
                    }
                }
            } catch (err) {
                console.error('Failed to check system status:', err);
            }
        };
        checkSystemStatus();
    }, []);

    const handlePauseClick = async () => {
        if (isPaused) {
            // Resume
            try {
                await fetch('/api/settings/pause_processing', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: 'pause_processing', value: 'false' })
                });
                setIsPaused(false);
            } catch (err) {
                console.error('Error resuming:', err);
            }
        } else {
            // Pause - check for active jobs first
            try {
                const response = await fetch('/api/jobs/active');
                if (response.ok) {
                    const jobs = await response.json();
                    if (jobs.running_count > 0) {
                        setActiveJobs(jobs);
                        setShowPauseDialog(true);
                    } else {
                        // No active jobs, pause immediately
                        await fetch('/api/settings/pause_processing', {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ key: 'pause_processing', value: 'true' })
                        });
                        setIsPaused(true);
                    }
                }
            } catch (err) {
                console.error('Error checking active jobs:', err);
            }
        }
    };

    const toggleAnalyticsPause = async () => {
        try {
            const response = await fetch('/api/analytics/toggle-pause', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            if (response.ok) {
                const result = await response.json();
                setAnalyticsPaused(result.paused);
                // Refresh status
                const statusRes = await fetch('/api/analytics/pause-status');
                if (statusRes.ok) {
                    const data = await statusRes.json();
                    setQueuedCount(data.queued_count);
                    setRunningJobId(data.running_job_id);
                }
            }
        } catch (error) {
            console.error('Error toggling analytics pause:', error);
        }
    };

    const toggleRunWhenIdle = async () => {
        try {
            const response = await fetch('/api/analytics/settings/run-when-idle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: !runWhenIdle })
            });
            if (response.ok) {
                const result = await response.json();
                setRunWhenIdle(result.enabled);
                showStatus(result.enabled ? 'Run when idle enabled' : 'Run when idle disabled');
            }
        } catch (error) {
            console.error('Error toggling run when idle:', error);
            showStatus('Failed to update setting', 'error');
        }
    };

    // Get available terms from all sessions
    const availableTerms = useMemo(() => {
        return getAvailableTerms(sessions);
    }, [sessions]);

    // Filter sessions based on search, term, faculty, and sort
    const filteredSessions = useMemo(() => {
        // First filter by search term
        let filtered = sessions.filter(session => {
            if (!searchTerm) return true;
            const term = searchTerm.toLowerCase();
            
            // Search in session name
            if (session.name?.toLowerCase().includes(term)) return true;
            
            // Search in analytics title and description (match by session_id)
            if (analyticsData && analyticsData.length > 0) {
                const sessionAnalytics = analyticsData.filter(a => a.session_id === session.id);
                
                for (const analytics of sessionAnalytics) {
                    if (analytics.title?.toLowerCase().includes(term)) return true;
                    if (analytics.description?.toLowerCase().includes(term)) return true;
                }
            }
            
            return false;
        });

        // Filter by faculty (only in analytics view)
        if (viewMode === 'analytics' && facultyFilter) {
            filtered = filtered.filter(session => {
                if (!analyticsData || analyticsData.length === 0) return false;
                const sessionAnalytics = analyticsData.filter(a => a.session_id === session.id);
                return sessionAnalytics.some(a => a.faculty === facultyFilter);
            });
        }

        // Filter by content type (only in analytics view)
        if (viewMode === 'analytics' && contentTypeFilter) {
            filtered = filtered.filter(session => {
                if (!analyticsData || analyticsData.length === 0) return false;
                const sessionAnalytics = analyticsData.filter(a => a.session_id === session.id);
                return sessionAnalytics.some(a => a.content_type === contentTypeFilter);
            });
        }

        // Then filter by selected term (only in grid view)
        if (layoutView === 'grid' && selectedTerm) {
            filtered = filtered.filter(session => {
                const termInfo = getTermForDate(session.recording_date);
                if (!termInfo) return false;
                return `${termInfo.year}-${termInfo.term}` === selectedTerm;
            });
        }

        // Then sort using centralized logic
        return sortSessions(filtered, sortOption);
    }, [sessions, searchTerm, sortOption, selectedTerm, layoutView, analyticsData, viewMode, facultyFilter, contentTypeFilter]);

    // Group sessions by term for grid view sticky headers
    const groupedSessionsByTerm = useMemo(() => {
        if (layoutView !== 'grid') return [];
        
        const groups = {};
        filteredSessions.forEach(session => {
            const termInfo = getTermForDate(session.recording_date);
            if (termInfo) {
                const key = `${termInfo.year}-${termInfo.term}`;
                const label = `${termInfo.year} - ${termInfo.label}`;
                if (!groups[key]) {
                    groups[key] = {
                        key,
                        label,
                        year: termInfo.year,
                        term: termInfo.term,
                        sessions: []
                    };
                }
                groups[key].sessions.push(session);
            } else {
                // Handle sessions without a valid date
                const key = 'unknown';
                if (!groups[key]) {
                    groups[key] = {
                        key,
                        label: 'Unknown Date',
                        year: 0,
                        term: 0,
                        sessions: []
                    };
                }
                groups[key].sessions.push(session);
            }
        });
        
        // Sort groups by year desc, then term desc
        return Object.values(groups).sort((a, b) => {
            if (a.year !== b.year) return b.year - a.year;
            return b.term - a.term;
        });
    }, [filteredSessions, layoutView]);

    return (
        <div className="flex flex-col h-full">
            {/* Maintenance Modal */}
            <MaintenanceModal
                isOpen={maintenanceMode}
                issues={maintenanceIssues}
            />

            <StatusOverlay
                isVisible={statusOverlay.visible}
                message={statusOverlay.message}
                type={statusOverlay.type}
                onHide={() => setStatusOverlay(prev => ({ ...prev, visible: false }))}
            />

            <div className="flex flex-row h-full overflow-hidden">
                {/* Side Panel */}
                <SidePanel
                    isPipelinePaused={isPaused}
                    onTogglePipelinePause={handlePauseClick}
                    isAnalyticsPaused={analyticsPaused}
                    onToggleAnalyticsPause={toggleAnalyticsPause}
                    aiEnabled={aiEnabled}
                    queuedCount={queuedCount}
                    runningJobId={runningJobId}
                    runWhenIdle={runWhenIdle}
                    onToggleRunWhenIdle={toggleRunWhenIdle}
                    analyticsStartHour={analyticsStartHour}
                    analyticsEndHour={analyticsEndHour}
                    onUpdateAnalyticsSchedule={handleUpdateAnalyticsSchedule}
                    analyticsScheduleEnabled={analyticsScheduleEnabled}
                    onToggleAnalyticsSchedule={toggleAnalyticsSchedule}
                    validationStatus={validationStatus}
                    ftpConnectionState={ftpConnectionState}
                    ftpHost={ftpHost}
                    ftpPort={ftpPort}
                    ftpErrorMessage={ftpErrorMessage}
                    onOpenSettings={onOpenSettings}
                />

                {/* Main Content Area */}
                <div className="flex-1 flex flex-col h-full overflow-hidden">
                    {/* Tabs */}
                    <div className="bg-white border-b border-gray-200 px-4 flex items-center justify-between shrink-0">
                        <div className="flex space-x-6">
                            <button
                                onClick={() => setMainView('files')}
                                className={`py-3 px-1 border-b-2 font-medium text-sm transition-colors ${mainView === 'files'
                                    ? 'border-blue-600 text-blue-600'
                                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                                    }`}
                            >
                                Files
                            </button>
                            {/* AI-only tabs: Spreadsheet, Analytics, Dev Queue */}
                            {aiEnabled && (
                                <>
                                    <button
                                        onClick={() => setMainView('spreadsheet')}
                                        className={`py-3 px-1 border-b-2 font-medium text-sm transition-colors ${mainView === 'spreadsheet'
                                            ? 'border-blue-600 text-blue-600'
                                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                                            }`}
                                    >
                                        Spreadsheet
                                    </button>
                                    <button
                                        onClick={() => setMainView('analytics')}
                                        className={`py-3 px-1 border-b-2 font-medium text-sm transition-colors ${mainView === 'analytics'
                                            ? 'border-blue-600 text-blue-600'
                                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                                            }`}
                                    >
                                        Analytics
                                    </button>
                                    <button
                                        onClick={() => setMainView('devqueue')}
                                        className={`py-3 px-1 border-b-2 font-medium text-sm transition-colors ${mainView === 'devqueue'
                                            ? 'border-blue-600 text-blue-600'
                                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                                            }`}
                                    >
                                        Dev Queue
                                    </button>
                                </>
                            )}
                        </div>
                        <WebSocketStatus />
                    </div>

                    {/* Content */}
                    <div className="flex-1 overflow-hidden bg-gray-50 relative">
                        {mainView === 'files' && (
                            <div className="h-full flex flex-col">
                                <SessionToolbar
                                    searchTerm={searchTerm}
                                    onSearchChange={setSearchTerm}
                                    sortOption={sortOption}
                                    onSortChange={handleSortChange}
                                    totalSessions={filteredSessions.length}
                                    viewMode={viewMode}
                                    onViewModeChange={setViewMode}
                                    aiEnabled={aiEnabled}
                                    layoutView={layoutView}
                                    onLayoutViewChange={setLayoutView}
                                    selectedTerm={selectedTerm}
                                    onSelectedTermChange={setSelectedTerm}
                                    availableTerms={availableTerms}
                                    facultyFilter={facultyFilter}
                                    onFacultyFilterChange={setFacultyFilter}
                                    contentTypeFilter={contentTypeFilter}
                                    onContentTypeFilterChange={setContentTypeFilter}
                                />

                                {selectMode.isSelectMode && (
                                    <SelectModeToolbar
                                        selectedCount={selectMode.selectedCount}
                                        totalCount={filteredSessions.length}
                                        onSelectAll={() => selectMode.selectAll(filteredSessions.map(s => s.id))}
                                        onDeselectAll={selectMode.clearSelection}
                                        onCancel={selectMode.exitSelectMode}
                                        activeTab={viewMode}
                                        onRemoveFromDatabase={async () => {
                                            if (!confirm(`Are you sure you want to delete ${selectMode.selectedCount} sessions from the database? This cannot be undone.`)) return;
                                            try {
                                                const res = await fetch('/api/sessions/bulk-delete', {
                                                    method: 'POST',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ session_ids: selectMode.selectedIds })
                                                });
                                                if (res.ok) {
                                                    showStatus(`Deleted ${selectMode.selectedCount} sessions`);
                                                    selectMode.exitSelectMode();
                                                    fetchSessions();
                                                } else {
                                                    showStatus('Failed to delete sessions', 'error');
                                                }
                                            } catch (err) {
                                                console.error(err);
                                                showStatus('Error deleting sessions', 'error');
                                            }
                                        }}
                                        onMarkForDeletion={async () => {
                                            if (!confirm(`Are you sure you want to delete files for ${selectMode.selectedCount} sessions from the FTP server immediately?`)) return;
                                            try {
                                                const res = await fetch('/api/files/bulk-delete-immediately', {
                                                    method: 'POST',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ session_ids: selectMode.selectedIds })
                                                });
                                                if (res.ok) {
                                                    const data = await res.json();
                                                    showStatus(`Deleted files for ${data.processed_sessions} sessions`);
                                                    selectMode.exitSelectMode();
                                                    fetchSessions();
                                                } else {
                                                    showStatus('Failed to delete files', 'error');
                                                }
                                            } catch (err) {
                                                console.error(err);
                                                showStatus('Error deleting files', 'error');
                                            }
                                        }}
                                        onReTranscribe={async () => {
                                            if (!confirm(`Reprocess transcript for ${selectMode.selectedCount} sessions?`)) return;
                                            try {
                                                // Get file IDs from analyticsData by matching session IDs
                                                const fileIds = analyticsData
                                                    .filter(a => selectMode.selectedIds.includes(a.session_id))
                                                    .map(a => a.file_id);

                                                const res = await fetch('/api/analytics/bulk-re-transcribe', {
                                                    method: 'POST',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ file_ids: fileIds })
                                                });

                                                if (res.ok) {
                                                    showStatus(`Queued re-transcription for ${fileIds.length} files`);
                                                    selectMode.exitSelectMode();
                                                } else {
                                                    showStatus('Failed to queue re-transcription', 'error');
                                                }
                                            } catch (err) {
                                                console.error(err);
                                                showStatus('Error queuing re-transcription', 'error');
                                            }
                                        }}
                                        onReAnalyze={async () => {
                                            if (!confirm(`Reprocess analytics for ${selectMode.selectedCount} sessions?`)) return;
                                            try {
                                                // Get file IDs from analyticsData by matching session IDs
                                                const fileIds = analyticsData
                                                    .filter(a => selectMode.selectedIds.includes(a.session_id))
                                                    .map(a => a.file_id);

                                                const res = await fetch('/api/analytics/bulk-re-analyze', {
                                                    method: 'POST',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ file_ids: fileIds })
                                                });

                                                if (res.ok) {
                                                    showStatus(`Queued re-analysis for ${fileIds.length} files`);
                                                    selectMode.exitSelectMode();
                                                } else {
                                                    showStatus('Failed to queue re-analysis', 'error');
                                                }
                                            } catch (err) {
                                                console.error(err);
                                                showStatus('Error queuing re-analysis', 'error');
                                            }
                                        }}
                                        onChangeFaculty={async (faculty) => {
                                            if (!confirm(`Change faculty to "${faculty}" for ${selectMode.selectedCount} sessions?`)) return;
                                            try {
                                                // Get file IDs from analyticsData by matching session IDs
                                                const fileIds = analyticsData
                                                    .filter(a => selectMode.selectedIds.includes(a.session_id))
                                                    .map(a => a.file_id);

                                                const res = await fetch('/api/analytics/bulk-update-faculty', {
                                                    method: 'POST',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ file_ids: fileIds, value: faculty })
                                                });

                                                if (res.ok) {
                                                    const data = await res.json();
                                                    showStatus(data.message);
                                                    selectMode.exitSelectMode();
                                                    // Refresh analytics data
                                                    const refreshRes = await fetch('/api/analytics/?limit=10000');
                                                    if (refreshRes.ok) {
                                                        setAnalyticsData(await refreshRes.json());
                                                    }
                                                } else {
                                                    const err = await res.json();
                                                    showStatus(err.detail || 'Failed to update faculty', 'error');
                                                }
                                            } catch (err) {
                                                console.error(err);
                                                showStatus('Error updating faculty', 'error');
                                            }
                                        }}
                                        onChangeContentType={async (contentType) => {
                                            if (!confirm(`Change content type to "${contentType}" for ${selectMode.selectedCount} sessions?`)) return;
                                            try {
                                                // Get file IDs from analyticsData by matching session IDs
                                                const fileIds = analyticsData
                                                    .filter(a => selectMode.selectedIds.includes(a.session_id))
                                                    .map(a => a.file_id);

                                                const res = await fetch('/api/analytics/bulk-update-content-type', {
                                                    method: 'POST',
                                                    headers: { 'Content-Type': 'application/json' },
                                                    body: JSON.stringify({ file_ids: fileIds, value: contentType })
                                                });

                                                if (res.ok) {
                                                    const data = await res.json();
                                                    showStatus(data.message);
                                                    selectMode.exitSelectMode();
                                                    // Refresh analytics data
                                                    const refreshRes = await fetch('/api/analytics/?limit=10000');
                                                    if (refreshRes.ok) {
                                                        setAnalyticsData(await refreshRes.json());
                                                    }
                                                } else {
                                                    const err = await res.json();
                                                    showStatus(err.detail || 'Failed to update content type', 'error');
                                                }
                                            } catch (err) {
                                                console.error(err);
                                                showStatus('Error updating content type', 'error');
                                            }
                                        }}
                                    />
                                )}

                                <div className={`flex-1 overflow-y-auto ${layoutView === 'grid' ? 'px-4' : 'p-4'}`}>
                                    {loading ? (
                                        <div className="flex justify-center py-12">
                                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                                        </div>
                                    ) : filteredSessions.length === 0 ? (
                                        <div className="text-center py-12 text-gray-500">
                                            No sessions found
                                        </div>
                                    ) : layoutView === 'grid' ? (
                                        /* Grid View with Sticky Term Headers */
                                        <div>
                                            {(() => {
                                                // Create a flat list of session IDs for shift-click selection
                                                const allGridSessionIds = groupedSessionsByTerm.flatMap(g => g.sessions.map(s => s.id));
                                                let globalIndex = 0;
                                                
                                                return groupedSessionsByTerm.map((group, groupIndex) => (
                                                    <div key={group.key} className={groupIndex > 0 ? 'mt-6' : ''}>
                                                        {/* Sticky Term Header */}
                                                        <h3 className="text-lg font-bold text-gray-700 mb-4 flex items-center gap-2 sticky top-0 bg-gray-50 py-3 -mx-4 px-4 z-20 border-b border-gray-200">
                                                            <Calendar className="w-5 h-5 text-blue-500" />
                                                            {group.label}
                                                            <span className="text-xs font-normal text-gray-400 bg-white px-2 py-1 rounded-full border border-gray-200">
                                                                {group.sessions.length} {group.sessions.length === 1 ? 'session' : 'sessions'}
                                                            </span>
                                                        </h3>
                                                        {/* Grid of Cards */}
                                                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                                                            {group.sessions.map((session) => {
                                                                const currentIndex = globalIndex++;
                                                                return (
                                                                    <SessionGridCard
                                                                        key={session.id}
                                                                        session={session}
                                                                        analyticsData={analyticsData}
                                                                        selectMode={selectMode}
                                                                        index={currentIndex}
                                                                        sessionIds={allGridSessionIds}
                                                                    />
                                                                );
                                                            })}
                                                        </div>
                                                    </div>
                                                ));
                                            })()}
                                            {/* Bottom padding */}
                                            <div className="pb-4"></div>
                                        </div>
                                    ) : (
                                        /* List View */
                                        <div className="space-y-4">
                                            {(() => {
                                                const listSessionIds = filteredSessions.map(s => s.id);
                                                return filteredSessions.map((session, index) => (
                                                    <UnifiedSessionCard
                                                        key={session.id}
                                                        session={session}
                                                        mode={viewMode}
                                                        analyticsData={analyticsData}
                                                        isExpanded={expandedSessions.includes(session.id)}
                                                        onToggleExpand={() => {
                                                            setExpandedSessions(prev =>
                                                                prev.includes(session.id)
                                                                    ? prev.filter(id => id !== session.id)
                                                                    : [...prev, session.id]
                                                            );
                                                        }}
                                                        selectMode={selectMode}
                                                        setSelectedTranscript={setSelectedTranscript}
                                                        setSelectedRawOutput={setSelectedRawOutput}
                                                        index={index}
                                                        sessionIds={listSessionIds}
                                                    />
                                                ));
                                            })()}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {mainView === 'spreadsheet' && (
                            <AnalyticsSpreadsheetPreview />
                        )}

                        {mainView === 'analytics' && (
                            <AnalyticsView />
                        )}

                        {mainView === 'devqueue' && (
                            <DevQueueView />
                        )}
                    </div>
                </div>
            </div>

            {/* Pause Confirmation Dialog */}
            {showPauseDialog && activeJobs && (
                <PauseConfirmDialog
                    activeJobs={activeJobs}
                    onConfirm={async (choice) => {
                        try {
                            if (choice === 'reset') {
                                await fetch('/api/jobs/cancel-active', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' }
                                });
                            }

                            await fetch('/api/settings/pause_processing', {
                                method: 'PUT',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ key: 'pause_processing', value: 'true' })
                            });

                            setIsPaused(true);
                            setShowPauseDialog(false);
                            setActiveJobs(null);
                        } catch (err) {
                            console.error('Error pausing:', err);
                            alert('Failed to pause pipeline');
                        }
                    }}
                    onCancel={() => {
                        setShowPauseDialog(false);
                        setActiveJobs(null);
                    }}
                />
            )}

            {/* Transcript Modal */}
            {selectedTranscript && (
                <div
                    className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
                    onClick={() => setSelectedTranscript(null)}
                >
                    <div
                        className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[80vh] flex flex-col"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between p-4 border-b border-gray-200">
                            <h2 className="text-lg font-semibold text-gray-800">Transcript</h2>
                            <button onClick={() => setSelectedTranscript(null)} className="text-gray-500 hover:text-gray-700">Close</button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-6">
                            <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">{selectedTranscript.transcript}</p>
                        </div>
                    </div>
                </div>
            )}

            {/* Raw Output Modal */}
            {selectedRawOutput && (
                <div
                    className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
                    onClick={() => setSelectedRawOutput(null)}
                >
                    <div
                        className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[80vh] flex flex-col"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between p-4 border-b border-gray-200">
                            <h2 className="text-lg font-semibold text-gray-800">Raw LLM Output</h2>
                            <button onClick={() => setSelectedRawOutput(null)} className="text-gray-500 hover:text-gray-700">Close</button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-6 bg-gray-50">
                            <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono overflow-x-auto">
                                {selectedRawOutput.analysis_json ? JSON.stringify(JSON.parse(selectedRawOutput.analysis_json), null, 2) : 'No JSON data'}
                            </pre>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
