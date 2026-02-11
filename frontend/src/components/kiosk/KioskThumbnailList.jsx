/**
 * KioskThumbnailList - Scrollable list of video thumbnails
 * 
 * Features:
 * - Newest files at top
 * - Thumbnails fill panel width
 * - Duration overlay in corner (YouTube style)
 * - Click to select
 */

import { FileThumbnail } from '../FileThumbnail';
import { Loader2, Video } from 'lucide-react';

// Format duration as MM:SS or HH:MM:SS
function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return null;

  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hrs > 0) {
    return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function KioskThumbnailList({ files = [], selectedFile, onSelect, isLoading }) {
  // Sort by created_at descending (newest first)
  const sortedFiles = [...files].sort((a, b) => {
    const dateA = new Date(a.created_at || 0);
    const dateB = new Date(b.created_at || 0);
    return dateB - dateA;
  });

  if (isLoading) {
    return (
      <div className="thumbnail-list-loading">
        <Loader2 className="animate-spin" size={24} />
        <span>Loading videos...</span>
      </div>
    );
  }

  if (files.length === 0) {
    return (
      <div className="thumbnail-list-empty">
        <Video size={32} />
        <span>No videos available</span>
      </div>
    );
  }

  return (
    <>
      <div className="thumbnail-list">
        {sortedFiles.map((file) => (
          <ThumbnailCard
            key={file.id}
            file={file}
            isSelected={selectedFile?.id === file.id}
            onSelect={() => onSelect(file)}
          />
        ))}
      </div>
      <style>{`
        .thumbnail-list {
          flex: 1;
          overflow-y: auto;
          padding: 0.5rem;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        
        .thumbnail-list::-webkit-scrollbar {
          width: 6px;
        }
        
        .thumbnail-list::-webkit-scrollbar-track {
          background: transparent;
        }
        
        .thumbnail-list::-webkit-scrollbar-thumb {
          background: #333;
          border-radius: 3px;
        }
        
        .thumbnail-list::-webkit-scrollbar-thumb:hover {
          background: #444;
        }
        
        .thumbnail-list-loading,
        .thumbnail-list-empty {
          flex: 1;
          min-height: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 1rem;
          padding: 2rem;
          color: #666;
        }
      `}</style>
    </>
  );
}


// Get user-friendly status label for file state
function getStatusLabel(state) {
  switch (state) {
    case 'DISCOVERED':
      return 'Queued';
    case 'COPYING':
      return 'Copying...';
    case 'COPIED':
      return 'Copied';
    case 'PROCESSING':
      return 'Processing...';
    case 'PROCESSED':
      return 'Ready';
    case 'ORGANIZING':
      return 'Organising...';
    case 'COMPLETED':
      return 'Ready';
    default:
      return state;
  }
}

function ThumbnailCard({ file, isSelected, onSelect }) {
  const isReady = ['COMPLETED', 'PROCESSED'].includes(file.state);
  const isInProgress = ['DISCOVERED', 'COPYING', 'COPIED', 'PROCESSING', 'ORGANIZING'].includes(file.state);
  const duration = formatDuration(file.duration);
  const statusLabel = getStatusLabel(file.state);

  return (
    <>
      <div
        className={`thumbnail-card ${isSelected ? 'selected' : ''} ${isReady ? 'ready' : 'processing'}`}
        onClick={isReady ? onSelect : undefined}
      >
        <div className="thumbnail-image">
          {/* Show placeholder for in-progress files, real thumbnail for ready files */}
          {isInProgress ? (
            <div className="thumbnail-placeholder-status">
              <div className="status-icon">
                <Loader2 className="animate-spin" size={32} />
              </div>
              <div className="status-label">{statusLabel}</div>
              {file.processing_stage && (
                <div className="status-detail">{file.processing_stage}</div>
              )}
            </div>
          ) : (
            <FileThumbnail
              fileId={file.id}
              className="thumbnail-img"
              etag={file.thumbnail_generated_at ? new Date(file.thumbnail_generated_at).getTime() : null}
            />
          )}

          {/* Duration badge - YouTube style (only for ready files) */}
          {duration && isReady && (
            <div className="thumbnail-duration">
              {duration}
            </div>
          )}

          {/* Progress bar for in-progress files */}
          {isInProgress && (
            <div className="thumbnail-processing">
              <div
                className="thumbnail-progress-bar"
                style={{ width: `${file.processing_stage_progress || 0}%` }}
              />
            </div>
          )}
        </div>
      </div>
      <style>{`
        .thumbnail-card {
          position: relative;
          cursor: pointer;
          transition: transform 0.15s, box-shadow 0.15s;
          border-radius: 8px;
          overflow: hidden;
          flex-shrink: 0; /* Prevent squishing */
          min-height: 0; /* Allow auto height based on aspect ratio */
        }
        
        .thumbnail-card.ready:hover {
          transform: scale(1.02);
          box-shadow: 0 4px 12px rgba(0,0,0,0.4);
          z-index: 10;
        }
        
        .thumbnail-card.selected {
          box-shadow: 0 0 0 3px #3b82f6;
          z-index: 5;
        }
        
        /* Combined state: Selected AND Hovered */
        .thumbnail-card.selected:hover {
          box-shadow: 0 0 0 3px #3b82f6, 0 4px 12px rgba(0,0,0,0.5);
        }
        
        .thumbnail-card.processing {
          opacity: 0.85;
          cursor: not-allowed;
        }
        
        .thumbnail-image {
          position: relative;
          width: 100%;
          aspect-ratio: 16 / 9;
          background: #222;
          border-radius: 8px;
          overflow: hidden;
        }
        
        .thumbnail-img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        
        .thumbnail-placeholder {
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 0.5rem;
          background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
          color: #fff; /* Ensure icon is white/visible */
        }
        
        .thumbnail-placeholder svg {
          opacity: 0.7;
          filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5));
        }
        
        .thumbnail-placeholder-status {
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 0.5rem;
          background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
          color: #fff;
        }
        
        .thumbnail-placeholder-status .status-icon {
          color: #3b82f6;
        }
        
        .thumbnail-placeholder-status .status-label {
          font-size: 0.85rem;
          font-weight: 600;
          color: #fff;
          text-shadow: 0 1px 2px rgba(0,0,0,0.5);
        }
        
        .thumbnail-placeholder-status .status-detail {
          font-size: 0.7rem;
          color: #888;
          text-align: center;
          padding: 0 0.5rem;
          max-width: 100%;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        
        .placeholder-filename {
          font-size: 0.7rem;
          color: #888;
          text-align: center;
          padding: 0 0.5rem;
          opacity: 0.8;
        }
        
        .thumbnail-duration {
          position: absolute;
          bottom: 6px;
          right: 6px;
          background: rgba(0, 0, 0, 0.85);
          color: #fff;
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 0.75rem;
          font-weight: 500;
          font-family: 'Roboto', 'Inter', sans-serif;
          letter-spacing: 0.02em;
        }
        
        .thumbnail-processing {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          height: 3px;
          background: rgba(0,0,0,0.5);
        }
        
        .thumbnail-progress-bar {
          height: 100%;
          background: #3b82f6;
          transition: width 0.3s ease;
        }
        
        .animate-spin {
          animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </>
  );
}
