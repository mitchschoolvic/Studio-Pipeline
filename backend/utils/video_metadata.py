"""
Video metadata extraction utilities

Provides functions to extract video file metadata (duration, bitrate, etc.)
without requiring complex FFmpeg operations.
"""

import subprocess
import json
import logging
from pathlib import Path
from typing import Optional, Dict
from utils.ffmpeg_helper import get_ffprobe_path

logger = logging.getLogger(__name__)


def get_video_duration(file_path: str) -> Optional[float]:
    """
    Extract video duration using ffprobe.
    
    This is a lightweight operation that only reads file metadata,
    not the actual video stream.
    
    Args:
        file_path: Path to video file (local file system)
        
    Returns:
        Duration in seconds, or None if extraction fails
    """
    try:
        # Use bundled ffprobe to get duration from file metadata
        result = subprocess.run(
            [
                get_ffprobe_path(),
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                str(file_path)
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.warning(f"ffprobe failed for {file_path}: {result.stderr}")
            return None
        
        data = json.loads(result.stdout)
        duration_str = data.get('format', {}).get('duration')
        
        if duration_str:
            duration = float(duration_str)
            logger.debug(f"Extracted duration for {Path(file_path).name}: {duration:.2f}s")
            return duration
        else:
            logger.warning(f"No duration found in metadata for {file_path}")
            return None
            
    except subprocess.TimeoutExpired:
        logger.error(f"ffprobe timeout for {file_path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse ffprobe output for {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error extracting duration from {file_path}: {e}")
        return None


def get_video_metadata(file_path: str) -> Optional[Dict]:
    """
    Extract comprehensive video metadata using ffprobe.
    
    Args:
        file_path: Path to video file (local file system)
        
    Returns:
        Dictionary containing:
        - duration: Duration in seconds
        - size: File size in bytes
        - bitrate: Average bitrate in kbps
        - format: Container format
        Or None if extraction fails
    """
    try:
        result = subprocess.run(
            [
                get_ffprobe_path(),
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                str(file_path)
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.warning(f"ffprobe failed for {file_path}: {result.stderr}")
            return None
        
        data = json.loads(result.stdout)
        format_info = data.get('format', {})
        
        metadata = {
            'duration': float(format_info.get('duration', 0)),
            'size': int(format_info.get('size', 0)),
            'bitrate': float(format_info.get('bit_rate', 0)) / 1000,  # Convert to kbps
            'format': format_info.get('format_name', 'unknown')
        }
        
        logger.debug(f"Extracted metadata for {Path(file_path).name}: {metadata}")
        return metadata
        
    except Exception as e:
        logger.error(f"Error extracting metadata from {file_path}: {e}")
        return None


def calculate_bitrate_kbps(file_size_bytes: int, duration_seconds: float) -> float:
    """
    Calculate average bitrate from file size and duration.
    
    Args:
        file_size_bytes: File size in bytes
        duration_seconds: Duration in seconds
        
    Returns:
        Bitrate in kbps
    """
    if duration_seconds <= 0:
        return 0.0
    
    # bitrate (kbps) = (file_size_bytes * 8) / (duration_seconds * 1000)
    return (file_size_bytes * 8) / (duration_seconds * 1000)
