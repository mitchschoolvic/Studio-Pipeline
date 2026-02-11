import React, { useState, useEffect, useRef } from 'react';
import { 
    FolderOpen, 
    RefreshCw, 
    Upload, 
    Check, 
    X, 
    AlertCircle, 
    Settings,
    ChevronDown,
    ChevronRight,
    Film,
    FileAudio,
    Image,
    Loader2,
    Play,
    Square,
    Info,
    CheckCircle
} from 'lucide-react';

// Toast notification component
function Toast({ message, type, onClose }) {
    useEffect(() => {
        const timer = setTimeout(onClose, 3000);
        return () => clearTimeout(timer);
    }, [onClose]);
    
    return (
        <div className={`fixed bottom-4 right-4 flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg z-50 ${
            type === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
        }`}>
            {type === 'success' ? (
                <CheckCircle className="w-5 h-5" />
            ) : (
                <AlertCircle className="w-5 h-5" />
            )}
            <span>{message}</span>
            <button onClick={onClose} className="ml-2 hover:opacity-80">
                <X className="w-4 h-4" />
            </button>
        </div>
    );
}

export function DevQueueView() {
    // Settings state
    const [settings, setSettings] = useState({
        source_path: '',
        analytics_export_path: '',
        thumbnail_folder: '',
        generate_mp3_if_missing: true,
        update_existing_records: true
    });
    const [showSettings, setShowSettings] = useState(false);
    
    // Toast state
    const [toast, setToast] = useState(null);
    
    const showToast = (message, type = 'success') => {
        setToast({ message, type });
    };
    
    // Scan state
    const [sessions, setSessions] = useState([]);
    const [scanning, setScanning] = useState(false);
    const [scanError, setScanError] = useState(null);
    
    // Import state
    const [importStatus, setImportStatus] = useState(null);
    const [importing, setImporting] = useState(false);
    const [importProgress, setImportProgress] = useState({ current: 0, total: 0, currentSession: '' });
    
    // Selection state
    const [selectedSessions, setSelectedSessions] = useState(new Set());
    const [expandedSessions, setExpandedSessions] = useState(new Set());
    
    // Polling ref
    const pollIntervalRef = useRef(null);
    
    // Load settings on mount
    useEffect(() => {
        loadSettings();
    }, []);
    
    // Poll import status when importing
    useEffect(() => {
        if (importing) {
            pollIntervalRef.current = setInterval(checkImportStatus, 1000);
        } else {
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
                pollIntervalRef.current = null;
            }
        }
        return () => {
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
            }
        };
    }, [importing]);
    
    const loadSettings = async () => {
        try {
            const response = await fetch('/api/dev-queue/settings');
            if (response.ok) {
                const data = await response.json();
                setSettings(data);
            }
        } catch (error) {
            console.error('Failed to load settings:', error);
        }
    };
    
    const saveSettings = async (newSettings) => {
        try {
            const response = await fetch('/api/dev-queue/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings: newSettings })
            });
            if (response.ok) {
                setShowSettings(false);
                showToast('Settings saved successfully');
            } else {
                const error = await response.json();
                showToast(error.detail || 'Failed to save settings', 'error');
            }
        } catch (error) {
            console.error('Failed to save settings:', error);
            showToast('Failed to save settings', 'error');
        }
    };
    
    const handleScan = async () => {
        if (!settings.source_path) {
            setScanError('Please configure a source path in settings first');
            setShowSettings(true);
            return;
        }
        
        setScanning(true);
        setScanError(null);
        setSessions([]);
        setSelectedSessions(new Set());
        
        try {
            const response = await fetch('/api/dev-queue/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_path: settings.source_path })
            });
            
            if (response.ok) {
                const data = await response.json();
                setSessions(data.sessions || []);
                // Auto-select all sessions
                setSelectedSessions(new Set(data.sessions.map(s => s.session_key)));
                showToast(`Found ${data.sessions?.length || 0} sessions`);
            } else {
                const error = await response.json();
                const errorMsg = typeof error.detail === 'string' 
                    ? error.detail 
                    : (error.detail?.[0]?.msg || 'Scan failed');
                setScanError(errorMsg);
                showToast(errorMsg, 'error');
            }
        } catch (error) {
            setScanError(error.message || 'Failed to scan folder');
            showToast(error.message || 'Failed to scan folder', 'error');
        } finally {
            setScanning(false);
        }
    };
    
    const handleImport = async () => {
        if (selectedSessions.size === 0) {
            return;
        }
        
        const sessionKeys = Array.from(selectedSessions);
        
        setImporting(true);
        setImportProgress({ current: 0, total: sessionKeys.length, currentSession: '' });
        
        try {
            const response = await fetch('/api/dev-queue/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    folder_path: settings.source_path,
                    session_keys: sessionKeys,
                    settings: settings
                })
            });
            
            if (!response.ok) {
                const error = await response.json();
                const errorMsg = typeof error.detail === 'string' 
                    ? error.detail 
                    : (error.detail?.[0]?.msg || 'Import failed');
                setScanError(errorMsg);
                showToast(errorMsg, 'error');
                setImporting(false);
            }
            // If successful, polling will handle progress updates
        } catch (error) {
            setScanError(error.message || 'Failed to start import');
            showToast(error.message || 'Failed to start import', 'error');
            setImporting(false);
        }
    };
    
    const checkImportStatus = async () => {
        try {
            const response = await fetch('/api/dev-queue/status');
            if (response.ok) {
                const status = await response.json();
                setImportStatus(status);
                
                if (status.state === 'running') {
                    setImportProgress({
                        current: status.completed || 0,
                        total: status.total || 0,
                        currentSession: status.current_session || ''
                    });
                } else if (status.state === 'completed' || status.state === 'error') {
                    setImporting(false);
                    if (status.state === 'completed') {
                        // Clear imported sessions from the list
                        setSessions([]);
                        setSelectedSessions(new Set());
                        showToast(`Import completed successfully`);
                    }
                    if (status.state === 'error' && status.error) {
                        setScanError(status.error);
                        showToast(status.error, 'error');
                    }
                }
            }
        } catch (error) {
            console.error('Failed to check import status:', error);
        }
    };
    
    const handleCancelImport = async () => {
        try {
            await fetch('/api/dev-queue/cancel', { method: 'POST' });
            setImporting(false);
        } catch (error) {
            console.error('Failed to cancel import:', error);
        }
    };
    
    const toggleSession = (sessionKey) => {
        const newSelected = new Set(selectedSessions);
        if (newSelected.has(sessionKey)) {
            newSelected.delete(sessionKey);
        } else {
            newSelected.add(sessionKey);
        }
        setSelectedSessions(newSelected);
    };
    
    const toggleExpand = (sessionKey) => {
        const newExpanded = new Set(expandedSessions);
        if (newExpanded.has(sessionKey)) {
            newExpanded.delete(sessionKey);
        } else {
            newExpanded.add(sessionKey);
        }
        setExpandedSessions(newExpanded);
    };
    
    const selectAll = () => {
        setSelectedSessions(new Set(sessions.map(s => s.session_key)));
    };
    
    const selectNone = () => {
        setSelectedSessions(new Set());
    };
    
    return (
        <div className="h-full flex flex-col bg-gray-50">
            {/* Toast Notification */}
            {toast && (
                <Toast
                    message={toast.message}
                    type={toast.type}
                    onClose={() => setToast(null)}
                />
            )}
            
            {/* Header */}
            <div className="bg-white border-b border-gray-200 px-6 py-4 shrink-0">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <FolderOpen className="w-6 h-6 text-blue-600" />
                        <div>
                            <h1 className="text-xl font-semibold text-gray-900">Dev Queue</h1>
                            <p className="text-sm text-gray-500">Import already-processed files into the database</p>
                        </div>
                    </div>
                    <button
                        onClick={() => setShowSettings(!showSettings)}
                        className={`p-2 rounded-lg transition-colors ${
                            showSettings 
                                ? 'bg-blue-100 text-blue-600' 
                                : 'hover:bg-gray-100 text-gray-600'
                        }`}
                    >
                        <Settings className="w-5 h-5" />
                    </button>
                </div>
            </div>
            
            {/* Settings Panel */}
            {showSettings && (
                <div className="bg-white border-b border-gray-200 px-6 py-4">
                    <h2 className="text-sm font-semibold text-gray-700 mb-3">Import Settings</h2>
                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-600 mb-1">
                                Source Folder Path
                            </label>
                            <input
                                type="text"
                                value={settings.source_path}
                                onChange={(e) => setSettings({ ...settings, source_path: e.target.value })}
                                placeholder="/Volumes/External/Studio Recordings"
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            />
                            <p className="text-xs text-gray-500 mt-1">Root folder containing session subfolders</p>
                        </div>
                        
                        <div>
                            <label className="block text-sm font-medium text-gray-600 mb-1">
                                Analytics Export Path
                            </label>
                            <input
                                type="text"
                                value={settings.analytics_export_path}
                                onChange={(e) => setSettings({ ...settings, analytics_export_path: e.target.value })}
                                placeholder="/Volumes/External/AI_Analytics"
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            />
                            <p className="text-xs text-gray-500 mt-1">Where to export thumbnails and MP3 files for analytics</p>
                        </div>
                        
                        <div>
                            <label className="block text-sm font-medium text-gray-600 mb-1">
                                Thumbnail Subfolder Name
                            </label>
                            <input
                                type="text"
                                value={settings.thumbnail_folder}
                                onChange={(e) => setSettings({ ...settings, thumbnail_folder: e.target.value })}
                                placeholder="dev_import_thumbnails"
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            />
                        </div>
                        
                        <div className="flex items-center gap-6">
                            <label className="flex items-center gap-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={settings.generate_mp3_if_missing}
                                    onChange={(e) => setSettings({ ...settings, generate_mp3_if_missing: e.target.checked })}
                                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                                />
                                <span className="text-sm text-gray-700">Generate MP3 if missing</span>
                            </label>
                            
                            <label className="flex items-center gap-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={settings.update_existing_records}
                                    onChange={(e) => setSettings({ ...settings, update_existing_records: e.target.checked })}
                                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                                />
                                <span className="text-sm text-gray-700">Update existing database records</span>
                            </label>
                        </div>
                        
                        <div className="flex justify-end gap-2">
                            <button
                                onClick={() => setShowSettings(false)}
                                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={() => saveSettings(settings)}
                                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                            >
                                Save Settings
                            </button>
                        </div>
                    </div>
                </div>
            )}
            
            {/* Action Bar */}
            <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-4">
                    <button
                        onClick={handleScan}
                        disabled={scanning || importing}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        {scanning ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                            <RefreshCw className="w-4 h-4" />
                        )}
                        {scanning ? 'Scanning...' : 'Scan Folder'}
                    </button>
                    
                    {sessions.length > 0 && (
                        <>
                            <button
                                onClick={selectAll}
                                disabled={importing}
                                className="text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50"
                            >
                                Select All
                            </button>
                            <button
                                onClick={selectNone}
                                disabled={importing}
                                className="text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50"
                            >
                                Select None
                            </button>
                        </>
                    )}
                </div>
                
                <div className="flex items-center gap-4">
                    {sessions.length > 0 && (
                        <span className="text-sm text-gray-500">
                            {selectedSessions.size} of {sessions.length} sessions selected
                        </span>
                    )}
                    
                    {importing ? (
                        <button
                            onClick={handleCancelImport}
                            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                        >
                            <Square className="w-4 h-4" />
                            Cancel Import
                        </button>
                    ) : (
                        <button
                            onClick={handleImport}
                            disabled={selectedSessions.size === 0 || scanning}
                            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            <Upload className="w-4 h-4" />
                            Import Selected
                        </button>
                    )}
                </div>
            </div>
            
            {/* Import Progress */}
            {importing && (
                <div className="bg-blue-50 border-b border-blue-200 px-6 py-4">
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                            <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
                            <span className="text-sm font-medium text-blue-800">
                                Importing: {importProgress.currentSession}
                            </span>
                        </div>
                        <span className="text-sm text-blue-600">
                            {importProgress.current} / {importProgress.total}
                        </span>
                    </div>
                    <div className="w-full bg-blue-200 rounded-full h-2">
                        <div 
                            className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                            style={{ 
                                width: `${importProgress.total > 0 ? (importProgress.current / importProgress.total) * 100 : 0}%` 
                            }}
                        />
                    </div>
                </div>
            )}
            
            {/* Error Display */}
            {scanError && (
                <div className="bg-red-50 border-b border-red-200 px-6 py-3 flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-red-600" />
                    <span className="text-sm text-red-700">{scanError}</span>
                    <button
                        onClick={() => setScanError(null)}
                        className="ml-auto text-red-600 hover:text-red-800"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            )}
            
            {/* Session List */}
            <div className="flex-1 overflow-auto p-6">
                {sessions.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-gray-500">
                        {scanning ? (
                            <>
                                <Loader2 className="w-12 h-12 text-blue-600 animate-spin mb-4" />
                                <p>Scanning folder for sessions...</p>
                            </>
                        ) : (
                            <>
                                <FolderOpen className="w-12 h-12 text-gray-400 mb-4" />
                                <p className="text-lg font-medium">No sessions found</p>
                                <p className="text-sm mt-1">Configure a source path and click "Scan Folder" to discover sessions</p>
                            </>
                        )}
                    </div>
                ) : (
                    <div className="space-y-3">
                        {sessions.map((session) => (
                            <SessionCard
                                key={session.session_key}
                                session={session}
                                selected={selectedSessions.has(session.session_key)}
                                expanded={expandedSessions.has(session.session_key)}
                                onToggleSelect={() => toggleSession(session.session_key)}
                                onToggleExpand={() => toggleExpand(session.session_key)}
                                disabled={importing}
                            />
                        ))}
                    </div>
                )}
            </div>
            
            {/* Import Results */}
            {importStatus?.state === 'completed' && importStatus.results && (
                <div className="bg-green-50 border-t border-green-200 px-6 py-4">
                    <div className="flex items-center gap-2 mb-2">
                        <Check className="w-5 h-5 text-green-600" />
                        <span className="font-medium text-green-800">Import Complete</span>
                    </div>
                    <div className="grid grid-cols-3 gap-4 text-sm">
                        <div>
                            <span className="text-gray-500">Sessions:</span>
                            <span className="ml-2 font-medium text-gray-900">{importStatus.results.sessions_imported}</span>
                        </div>
                        <div>
                            <span className="text-gray-500">Files:</span>
                            <span className="ml-2 font-medium text-gray-900">{importStatus.results.files_imported}</span>
                        </div>
                        <div>
                            <span className="text-gray-500">Skipped:</span>
                            <span className="ml-2 font-medium text-gray-900">{importStatus.results.files_skipped}</span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// Session Card Component
function SessionCard({ session, selected, expanded, onToggleSelect, onToggleExpand, disabled }) {
    const mainFiles = session.files?.filter(f => f.type === 'main') || [];
    const isoFiles = session.files?.filter(f => f.type === 'iso') || [];
    const hasAudio = session.files?.some(f => f.has_mp3);
    
    return (
        <div className={`bg-white rounded-lg border ${selected ? 'border-blue-400 ring-2 ring-blue-100' : 'border-gray-200'} overflow-hidden`}>
            {/* Header */}
            <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 border-b border-gray-200">
                <input
                    type="checkbox"
                    checked={selected}
                    onChange={onToggleSelect}
                    disabled={disabled}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 disabled:opacity-50"
                />
                
                <button
                    onClick={onToggleExpand}
                    className="text-gray-500 hover:text-gray-700"
                >
                    {expanded ? (
                        <ChevronDown className="w-4 h-4" />
                    ) : (
                        <ChevronRight className="w-4 h-4" />
                    )}
                </button>
                
                <div className="flex-1">
                    <div className="font-medium text-gray-900">{session.session_name}</div>
                    <div className="text-xs text-gray-500">{session.folder_path}</div>
                </div>
                
                <div className="flex items-center gap-4 text-sm text-gray-500">
                    <div className="flex items-center gap-1" title="Main video files">
                        <Film className="w-4 h-4" />
                        <span>{mainFiles.length}</span>
                    </div>
                    {isoFiles.length > 0 && (
                        <div className="flex items-center gap-1" title="ISO camera files">
                            <Film className="w-4 h-4 text-orange-500" />
                            <span>{isoFiles.length}</span>
                        </div>
                    )}
                    {hasAudio && (
                        <div className="flex items-center gap-1" title="Has MP3 audio">
                            <FileAudio className="w-4 h-4 text-green-500" />
                        </div>
                    )}
                </div>
            </div>
            
            {/* Expanded File List */}
            {expanded && (
                <div className="divide-y divide-gray-100">
                    {session.files?.map((file, index) => (
                        <div key={index} className="px-4 py-2 flex items-center gap-3 text-sm">
                            <div className={`w-2 h-2 rounded-full ${
                                file.type === 'iso' ? 'bg-orange-400' : 'bg-blue-400'
                            }`} />
                            <span className="flex-1 font-mono text-gray-700">{file.filename}</span>
                            <div className="flex items-center gap-2 text-gray-400">
                                {file.type === 'iso' && (
                                    <span className="text-xs px-2 py-0.5 bg-orange-100 text-orange-700 rounded">
                                        {file.camera_id}
                                    </span>
                                )}
                                {file.has_mp3 && (
                                    <FileAudio className="w-4 h-4 text-green-500" title="MP3 exists" />
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

export default DevQueueView;
