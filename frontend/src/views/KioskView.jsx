/**
 * KioskView - Video Playback Kiosk
 * 
 * Fullscreen-optimized view for video playback with:
 * - Video player (center)
 * - Waveform visualization below player
 * - Thumbnail list (right side, newest at top)
 */

import { useState, useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { KioskVideoPlayer } from '../components/kiosk/KioskVideoPlayer';
import { KioskWaveform } from '../components/kiosk/KioskWaveform';
import { KioskThumbnailList } from '../components/kiosk/KioskThumbnailList';
import { useWebSocketContext } from '../contexts/WebSocketContext';
import { WebSocketStatus } from '../components/WebSocketStatus';

// Fetch all program output files (including in-progress) for kiosk display
async function fetchKioskFiles() {
    const response = await fetch('/api/files?is_program_output=true');
    if (!response.ok) throw new Error('Failed to fetch files');
    return response.json();
}

// Time filter options
const TIME_FILTERS = [
    { value: '2hours', label: 'Past 2 Hours' },
    { value: 'today', label: 'Today' },
    { value: 'week', label: 'This Week' },
    { value: 'all', label: 'All Time' },
];

// Parse a backend timestamp as UTC (backend uses datetime.utcnow which
// produces naive-UTC strings without a trailing 'Z').
function parseUTC(ts) {
    if (!ts) return new Date(0);
    if (!ts.endsWith('Z') && !ts.includes('+') && !ts.includes('-', 10)) {
        return new Date(ts + 'Z');
    }
    return new Date(ts);
}

// Filter files by time range
function filterFilesByTime(files, filterValue) {
    if (filterValue === 'all') return files;

    const now = new Date();
    let cutoff;

    switch (filterValue) {
        case '2hours':
            cutoff = new Date(now.getTime() - 2 * 60 * 60 * 1000);
            break;
        case 'today':
            cutoff = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            break;
        case 'week': {
            const dayOfWeek = now.getDay();
            const daysToMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
            cutoff = new Date(now.getFullYear(), now.getMonth(), now.getDate() - daysToMonday);
            break;
        }
        default:
            return files;
    }

    return files.filter(f => parseUTC(f.created_at) >= cutoff);
}

export function KioskView() {
    const [selectedFile, setSelectedFile] = useState(null);
    const [timeFilter, setTimeFilter] = useState('2hours');
    const [filterOpen, setFilterOpen] = useState(false);
    const filterRef = useRef(null);
    const videoRef = useRef(null);
    const queryClient = useQueryClient();
    const { lastMessage } = useWebSocketContext();

    // Close filter dropdown when tapping outside
    useEffect(() => {
        if (!filterOpen) return;
        const handleClickOutside = (e) => {
            if (filterRef.current && !filterRef.current.contains(e.target)) {
                setFilterOpen(false);
            }
        };
        document.addEventListener('pointerdown', handleClickOutside);
        return () => document.removeEventListener('pointerdown', handleClickOutside);
    }, [filterOpen]);

    // Fetch files for thumbnail list
    const { data: files = [], isLoading } = useQuery({
        queryKey: ['kiosk-files'],
        queryFn: fetchKioskFiles,
        refetchInterval: 30000, // Refresh every 30 seconds as backup
    });

    // Handle WebSocket messages for real-time updates
    useEffect(() => {
        if (!lastMessage) return;

        switch (lastMessage.type) {
            case 'file_state_change':
                // Invalidate file list on any state change to show processing progress
                queryClient.invalidateQueries({ queryKey: ['kiosk-files'] });
                break;

            case 'thumbnail_update':
                // Refresh thumbnails when ready
                if (lastMessage.data?.thumbnail_state === 'READY') {
                    queryClient.invalidateQueries({ queryKey: ['kiosk-files'] });
                }
                break;

            case 'waveform_update':
                // Refresh waveform when ready
                if (lastMessage.data?.waveform_state === 'READY' && selectedFile?.id === lastMessage.data.file_id) {
                    queryClient.invalidateQueries({ queryKey: ['waveform', lastMessage.data.file_id] });
                }
                break;

            case 'session_discovered':
            case 'session.created':
                // A new session was discovered, refresh file list
                queryClient.invalidateQueries({ queryKey: ['kiosk-files'] });
                break;

            case 'session.deleted':
                // A session was deleted, refresh file list to remove deleted files
                queryClient.invalidateQueries({ queryKey: ['kiosk-files'] });
                break;
        }
    }, [lastMessage, queryClient, selectedFile?.id]);

    // Handle video seek from waveform
    const handleWaveformSeek = (time) => {
        if (videoRef.current) {
            videoRef.current.currentTime = time;
        }
    };

    // Video duration state (currentTime is read directly by KioskWaveform via videoRef)
    const [duration, setDuration] = useState(0);
    const [isPlaying, setIsPlaying] = useState(false);

    // Handle play state changes from video player
    const handlePlayStateChange = (playing) => {
        setIsPlaying(playing);
    };

    // Toggle play/pause
    const togglePlayPause = () => {
        if (!videoRef.current) return;
        if (videoRef.current.paused()) {
            videoRef.current.play();
        } else {
            videoRef.current.pause();
        }
    };

    // Apply time filter to files
    const filteredFiles = filterFilesByTime(files, timeFilter);

    // Auto-select first file if none selected or selected file not in filtered list
    useEffect(() => {
        if (filteredFiles.length > 0 && (!selectedFile || !filteredFiles.find(f => f.id === selectedFile?.id))) {
            setSelectedFile(filteredFiles[0]);
        }
    }, [filteredFiles, selectedFile]);

    return (
        <div className="kiosk-container">
            {/* Main content area */}
            <div className="kiosk-main">
                {/* Video Player */}
                <div className="kiosk-player">
                    {selectedFile ? (
                        <KioskVideoPlayer
                            file={selectedFile}
                            ref={videoRef}
                            onDurationChange={setDuration}
                            onPlayStateChange={handlePlayStateChange}
                        />
                    ) : (
                        <div className="kiosk-player-empty">
                            <span>Select a video to play</span>
                        </div>
                    )}
                </div>

                {/* Waveform */}
                <div className="kiosk-waveform-row">
                    {selectedFile && (
                        <button
                            className="kiosk-play-toggle"
                            onClick={togglePlayPause}
                            title={isPlaying ? 'Pause' : 'Play'}
                        >
                            {isPlaying ? (
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                                    <rect x="6" y="4" width="4" height="16" rx="1" />
                                    <rect x="14" y="4" width="4" height="16" rx="1" />
                                </svg>
                            ) : (
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M8 5v14l11-7z" />
                                </svg>
                            )}
                        </button>
                    )}
                    <div className="kiosk-waveform">
                        {selectedFile && (
                            <KioskWaveform
                                fileId={selectedFile.id}
                                videoPlayerRef={videoRef}
                                duration={duration}
                                onSeek={handleWaveformSeek}
                            />
                        )}
                    </div>
                </div>

                {/* Video info */}
                {selectedFile && (
                    <div className="kiosk-info">
                        <span className="kiosk-filename">{selectedFile.filename}</span>
                    </div>
                )}
            </div>

            {/* Thumbnail sidebar */}
            <div className="kiosk-sidebar">
                <div className="kiosk-sidebar-header">
                    <span>Videos</span>
                    <span className="kiosk-file-count">{filteredFiles.length}</span>
                </div>

                {/* Time filter dropdown — touchscreen friendly */}
                <div className="kiosk-filter-wrapper" ref={filterRef}>
                    <button
                        className="kiosk-filter-button"
                        onClick={() => setFilterOpen(prev => !prev)}
                    >
                        <span className="kiosk-filter-label">{TIME_FILTERS.find(f => f.value === timeFilter)?.label}</span>
                        <span className={`kiosk-filter-chevron ${filterOpen ? 'open' : ''}`}>▾</span>
                    </button>
                    {filterOpen && (
                        <div className="kiosk-filter-dropdown">
                            {TIME_FILTERS.map(opt => (
                                <button
                                    key={opt.value}
                                    className={`kiosk-filter-option ${timeFilter === opt.value ? 'active' : ''}`}
                                    onClick={() => {
                                        setTimeFilter(opt.value);
                                        setFilterOpen(false);
                                    }}
                                >
                                    {opt.label}
                                    {timeFilter === opt.value && <span className="kiosk-filter-check">✓</span>}
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                <div className="kiosk-ws-status">
                    <WebSocketStatus />
                </div>
                <KioskThumbnailList
                    files={filteredFiles}
                    selectedFile={selectedFile}
                    onSelect={setSelectedFile}
                    isLoading={isLoading}
                />
            </div>

            {/* Kiosk styles */}
            <style>{`
        .kiosk-container {
          display: flex;
          width: 100vw;
          height: 100vh;
          background: #0a0a0a;
          color: white;
          overflow: hidden;
        }
        
        .kiosk-main {
          flex: 1;
          display: flex;
          flex-direction: column;
          padding: 1rem;
          gap: 0.5rem;
        }
        
        .kiosk-player {
          flex: 1;
          min-height: 0;
          background: #111;
          border-radius: 12px;
          overflow: hidden;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        
        .kiosk-player-empty {
          color: #666;
          font-size: 1.5rem;
        }
        
        .kiosk-waveform-row {
          display: flex;
          align-items: stretch;
          gap: 8px;
          height: 120px;
        }

        .kiosk-play-toggle {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 44px;
          min-width: 44px;
          background: #1a1a1a;
          border: 1px solid #333;
          border-radius: 8px;
          color: #fff;
          cursor: pointer;
          touch-action: manipulation;
          -webkit-tap-highlight-color: transparent;
          transition: background 0.15s, border-color 0.15s;
        }

        .kiosk-play-toggle:hover {
          background: #2a2a2a;
          border-color: #444;
        }

        .kiosk-play-toggle:active {
          background: #333;
        }

        .kiosk-waveform {
          flex: 1;
          min-width: 0;
          height: 120px;
          background: #111;
          border-radius: 8px;
          overflow: hidden;
        }
        
        .kiosk-info {
          padding: 0.5rem;
        }
        
        .kiosk-filename {
          font-size: 0.5rem;
          font-weight: 500;
        }
        
        .kiosk-sidebar {
          width: 320px;
          background: #111;
          border-left: 1px solid #222;
          display: flex;
          flex-direction: column;
        }
        
        .kiosk-sidebar-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 1rem;
          font-weight: 600;
          border-bottom: 1px solid #222;
        }
        
        .kiosk-file-count {
          background: #333;
          padding: 0.25rem 0.5rem;
          border-radius: 12px;
          font-size: 0.875rem;
        }
        
        .kiosk-ws-status {
          padding: 0.5rem 1rem;
          border-bottom: 1px solid #222;
        }

        /* Time filter — touchscreen-friendly */
        .kiosk-filter-wrapper {
          position: relative;
          padding: 0.5rem 0.75rem;
          border-bottom: 1px solid #222;
        }

        .kiosk-filter-button {
          display: flex;
          align-items: center;
          justify-content: space-between;
          width: 100%;
          min-height: 44px;
          padding: 0.5rem 0.75rem;
          background: #1a1a1a;
          border: 1px solid #333;
          border-radius: 8px;
          color: #fff;
          font-size: 0.95rem;
          font-weight: 500;
          cursor: pointer;
          touch-action: manipulation;
          -webkit-tap-highlight-color: transparent;
          transition: background 0.15s, border-color 0.15s;
        }

        .kiosk-filter-button:hover {
          background: #222;
          border-color: #444;
        }

        .kiosk-filter-button:active {
          background: #252525;
        }

        .kiosk-filter-chevron {
          font-size: 1rem;
          transition: transform 0.2s;
        }

        .kiosk-filter-chevron.open {
          transform: rotate(180deg);
        }

        .kiosk-filter-dropdown {
          position: absolute;
          top: calc(100% - 2px);
          left: 0.75rem;
          right: 0.75rem;
          background: #1e1e1e;
          border: 1px solid #333;
          border-radius: 8px;
          z-index: 100;
          overflow: hidden;
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
          animation: kioskFilterSlide 0.15s ease-out;
        }

        @keyframes kioskFilterSlide {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }

        .kiosk-filter-option {
          display: flex;
          align-items: center;
          justify-content: space-between;
          width: 100%;
          min-height: 48px;
          padding: 0.75rem 1rem;
          background: none;
          border: none;
          border-bottom: 1px solid #2a2a2a;
          color: #ccc;
          font-size: 0.95rem;
          cursor: pointer;
          touch-action: manipulation;
          -webkit-tap-highlight-color: transparent;
          transition: background 0.1s;
        }

        .kiosk-filter-option:last-child {
          border-bottom: none;
        }

        .kiosk-filter-option:hover {
          background: #2a2a2a;
        }

        .kiosk-filter-option:active {
          background: #333;
        }

        .kiosk-filter-option.active {
          color: #3b82f6;
          font-weight: 600;
        }

        .kiosk-filter-check {
          color: #3b82f6;
          font-size: 1rem;
        }
      `}</style>
        </div>
    );
}
