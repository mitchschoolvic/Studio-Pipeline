"""
Video Streaming API Endpoints

Provides byte-range streaming for video files to enable smooth scrubbing
without full file downloads.
"""

import os
import mimetypes
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session

from models import File
from database import get_db

router = APIRouter()


def get_video_path(file: File) -> Path | None:
    """Get the best available video path for a file."""
    # Priority: final > processed > local
    for path_attr in ['path_final', 'path_processed', 'path_local']:
        path_str = getattr(file, path_attr, None)
        if path_str:
            path = Path(path_str)
            if path.exists():
                return path
    return None


def create_range_response(file_path: Path, range_header: str):
    """
    Create a streaming response for HTTP Range requests.
    
    This enables browser-native seeking without downloading the full file.
    Essential for smooth scrubbing in video players.
    """
    file_size = file_path.stat().st_size
    
    # Parse range header: "bytes=0-1023" or "bytes=0-"
    range_spec = range_header.replace("bytes=", "")
    
    if "-" in range_spec:
        parts = range_spec.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
    else:
        start = int(range_spec)
        end = file_size - 1
    
    # Clamp to valid range
    start = max(0, min(start, file_size - 1))
    end = max(start, min(end, file_size - 1))
    
    content_length = end - start + 1
    
    def iter_file():
        """Generator to stream file chunks."""
        with open(file_path, 'rb') as f:
            f.seek(start)
            remaining = content_length
            chunk_size = 64 * 1024  # 64KB chunks
            
            while remaining > 0:
                read_size = min(chunk_size, remaining)
                data = f.read(read_size)
                if not data:
                    break
                remaining -= len(data)
                yield data
    
    # Determine content type
    content_type, _ = mimetypes.guess_type(str(file_path))
    if not content_type:
        content_type = "video/mp4"
    
    return StreamingResponse(
        iter_file(),
        status_code=206,  # Partial Content
        media_type=content_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(content_length),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",  # 1 hour cache
        }
    )


@router.get("/videos/{file_id}/stream")
async def stream_video(
    file_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Stream video with HTTP Range header support.
    
    Enables browser-native seeking without downloading the full file.
    Falls back to full file response if no Range header is present.
    
    Args:
        file_id: UUID of the file
        request: FastAPI request object (for Range header)
    """
    file = db.query(File).filter(File.id == file_id).first()
    
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    video_path = get_video_path(file)
    
    if not video_path:
        raise HTTPException(
            status_code=404,
            detail="Video file not available. File may still be processing."
        )
    
    range_header = request.headers.get("range")
    
    if range_header:
        # Serve partial content for seeking
        return create_range_response(video_path, range_header)
    else:
        # Serve full file with Accept-Ranges header
        content_type, _ = mimetypes.guess_type(str(video_path))
        if not content_type:
            content_type = "video/mp4"
        
        return FileResponse(
            str(video_path),
            media_type=content_type,
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600",
            }
        )


@router.get("/videos/{file_id}/info")
async def get_video_info(file_id: str, db: Session = Depends(get_db)):
    """
    Get video file metadata.
    
    Returns file info including available paths and readiness state.
    """
    file = db.query(File).filter(File.id == file_id).first()
    
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    video_path = get_video_path(file)
    
    return {
        "file_id": file_id,
        "filename": file.filename,
        "state": file.state,
        "duration": file.duration,
        "size": file.size,
        "is_available": video_path is not None,
        "waveform_state": file.waveform_state,
        "thumbnail_state": file.thumbnail_state,
    }
