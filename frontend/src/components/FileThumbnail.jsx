/**
 * FileThumbnail Component
 * 
 * Displays video thumbnails with loading states and placeholders.
 * Uses native browser lazy loading for performance with many thumbnails.
 */

import React, { useState } from 'react';
import { FileVideo, AlertCircle } from 'lucide-react';

import { isThumbnailLoaded, markThumbnailLoaded } from '../utils/thumbnailCache';

export function FileThumbnail({
  fileId,
  isEmpty = false,
  className = "",
  etag = null
}) {
  const [imageLoaded, setImageLoaded] = useState(() => isThumbnailLoaded(fileId));
  const [imageError, setImageError] = useState(false);
  
  // Build URL with optional cache buster
  const imgUrl = fileId ? `/api/thumbnails/${fileId}${etag ? `?t=${etag}` : ''}` : null;

  const handleLoad = () => {
    setImageLoaded(true);
    setImageError(false);
    if (fileId) markThumbnailLoaded(fileId);
  };

  const handleError = () => {
    setImageError(true);
    setImageLoaded(false);
  };

  // Empty file placeholder
  if (isEmpty) {
    return (
      <div className={`bg-gray-200 flex items-center justify-center ${className}`} style={{ aspectRatio: '16/9' }}>
        <div className="text-center text-gray-500">
          <AlertCircle className="mx-auto mb-1" size={20} />
          <span className="text-xs font-medium">Empty</span>
        </div>
      </div>
    );
  }

  // No file ID
  if (!fileId) {
    return (
      <div className={`bg-gray-100 flex items-center justify-center ${className}`} style={{ aspectRatio: '16/9' }}>
        <FileVideo className="text-gray-400" size={24} />
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden bg-gray-100 ${className}`} style={{ aspectRatio: '16/9' }}>
      {/* Always render the img tag - browser handles loading */}
      {!imageError && (
        <img
          src={imgUrl}
          alt="Thumbnail"
          className={`w-full h-full object-cover transition-opacity duration-200 ${imageLoaded ? 'opacity-100' : 'opacity-0'}`}
          onLoad={handleLoad}
          onError={handleError}
          loading="lazy"
        />
      )}
      {/* Loading/error overlay */}
      {(!imageLoaded || imageError) && (
        <div className="absolute inset-0 flex items-center justify-center">
          {imageError ? (
            <FileVideo className="text-gray-400" size={24} />
          ) : (
            <div className="animate-pulse">
              <FileVideo className="text-gray-300" size={24} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}


/**
 * SessionThumbnail Component
 * 
 * Shows thumbnail for a session's primary file.
 * Falls back to first available file if primary not available.
 */
export function SessionThumbnail({ session, className = "" }) {
  // Get primary file (first file that isn't an ISO)
  const primaryFile = session.files?.find(f => !f.is_iso) || session.files?.[0];

  if (!primaryFile) {
    return (
      <div
        className={`bg-gray-100 flex items-center justify-center ${className}`}
        title="No files"
      >
        <FileVideo className="text-gray-400" size={24} />
      </div>
    );
  }

  return (
    <FileThumbnail
      fileId={primaryFile.id}
      isEmpty={primaryFile.is_empty}
      className={className}
    />
  );
}


/**
 * ThumbnailGrid Component
 * 
 * Display multiple thumbnails in a grid layout.
 * Useful for showing session's ISO files.
 */
export function ThumbnailGrid({ files, maxDisplay = 4, className = "" }) {
  const displayFiles = files.slice(0, maxDisplay);
  const remainingCount = files.length - maxDisplay;

  return (
    <div className={`grid grid-cols-2 gap-2 ${className}`}>
      {displayFiles.map((file, index) => (
        <FileThumbnail
          key={file.id}
          fileId={file.id}
          isEmpty={file.is_empty}
          className="w-full h-20 rounded"
        />
      ))}

      {remainingCount > 0 && (
        <div className="w-full h-20 bg-gray-100 rounded flex items-center justify-center">
          <span className="text-gray-600 font-medium">
            +{remainingCount} more
          </span>
        </div>
      )}
    </div>
  );
}
