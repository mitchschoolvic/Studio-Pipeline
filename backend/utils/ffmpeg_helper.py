"""
FFmpeg Binary Helper

Provides paths to bundled ffmpeg/ffprobe binaries.
Handles both development and PyInstaller bundled environments.

This module automatically sets the FFMPEG_BINARY environment variable
for mlx-whisper to use the bundled ffmpeg.
"""
import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_bundled_binary_path(binary_name: str) -> str:
    """
    Get path to bundled ffmpeg binary.
    
    Args:
        binary_name: 'ffmpeg' or 'ffprobe'
        
    Returns:
        Absolute path to the binary
        
    Raises:
        FileNotFoundError: If binary not found
    """
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        base_path = Path(sys._MEIPASS)
        binary_path = base_path / 'ffmpeg_bins' / binary_name
        logger.debug(f"Looking for bundled {binary_name} in PyInstaller bundle: {binary_path}")
    else:
        # Running in development
        base_path = Path(__file__).parent.parent.parent
        binary_path = base_path / 'ffmpeg_bins' / binary_name
        logger.debug(f"Looking for {binary_name} in development: {binary_path}")
    
    if not binary_path.exists():
        raise FileNotFoundError(
            f"Bundled {binary_name} not found at {binary_path}. "
            f"Please download from https://evermeet.cx/ffmpeg/ and place in ffmpeg_bins/"
        )
    
    logger.info(f"Using bundled {binary_name}: {binary_path}")
    return str(binary_path)


def get_ffmpeg_path() -> str:
    """Get path to bundled ffmpeg binary."""
    return get_bundled_binary_path('ffmpeg')


def get_ffprobe_path() -> str:
    """Get path to bundled ffprobe binary."""
    return get_bundled_binary_path('ffprobe')


def patch_mlx_whisper():
    """
    Monkey-patch mlx_whisper to use bundled ffmpeg binary.
    
    mlx_whisper.audio.load_audio hardcodes 'ffmpeg' command.
    We need to intercept this and replace it with our bundled binary path.
    """
    try:
        import mlx_whisper.audio
        
        # Get bundled ffmpeg path
        ffmpeg_path = get_ffmpeg_path()
        
        # Store original function just in case
        original_load_audio = mlx_whisper.audio.load_audio
        
        def patched_load_audio(file: str, sr: int = 16000, from_stdin=False):
            """
            Patched version of load_audio that uses bundled ffmpeg.
            """
            from subprocess import run, CalledProcessError
            import numpy as np
            import mlx.core as mx
            
            # Use bundled ffmpeg path instead of just "ffmpeg"
            if from_stdin:
                cmd = [ffmpeg_path, "-i", "pipe:0"]
            else:
                cmd = [ffmpeg_path, "-nostdin", "-i", file]

            # Rest of the implementation copied from mlx_whisper.audio.load_audio
            # to ensure exact behavior compatibility
            cmd.extend([
                "-threads", "0",
                "-f", "s16le",
                "-ac", "1",
                "-acodec", "pcm_s16le",
                "-ar", str(sr),
                "-"
            ])
            
            try:
                out = run(cmd, capture_output=True, check=True).stdout
            except CalledProcessError as e:
                raise RuntimeError(f"Failed to load audio: {e.stderr.decode()}") from e

            return mx.array(np.frombuffer(out, np.int16)).flatten().astype(mx.float32) / 32768.0
            
        # Apply patch
        mlx_whisper.audio.load_audio = patched_load_audio
        logger.info(f"✅ Monkey-patched mlx_whisper to use bundled ffmpeg: {ffmpeg_path}")
        
    except ImportError:
        logger.warning("Could not import mlx_whisper to patch it")
    except Exception as e:
        logger.error(f"Failed to patch mlx_whisper: {e}")


# Set environment variable for mlx-whisper to find ffmpeg
# mlx-whisper checks FFMPEG_BINARY environment variable first
try:
    ffmpeg_path = get_ffmpeg_path()
    os.environ['FFMPEG_BINARY'] = ffmpeg_path
    logger.info(f"Set FFMPEG_BINARY environment variable for mlx-whisper: {ffmpeg_path}")
except FileNotFoundError as e:
    logger.warning(f"Could not set FFMPEG_BINARY: {e}")
    # Don't raise - let the actual usage fail with a clear error message
