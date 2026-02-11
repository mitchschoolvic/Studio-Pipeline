"""
Waveform Generator Service

Generates audio waveform peaks using bundled FFmpeg for Wavesurfer.js visualization.
Designed for parallel execution during the processing pipeline.
"""

import subprocess
import json
import logging
import struct
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
from models import File
from utils.ffmpeg_helper import get_ffmpeg_path, get_ffprobe_path

logger = logging.getLogger(__name__)


class WaveformGenerator:
    """
    Generates waveform peak data from audio files using FFmpeg.
    
    Output format is JSON compatible with Wavesurfer.js:
    {
        "peaks": [0.0-1.0 normalized values],
        "duration": float (seconds),
        "sample_rate": int
    }
    """
    
    def __init__(self, waveform_dir: str, peak_count: int = 800):
        """
        Initialize waveform generator.
        
        Args:
            waveform_dir: Directory to store generated waveform JSON files
            peak_count: Number of peaks to generate (800 is good for responsive rendering)
        """
        self.waveform_dir = Path(waveform_dir)
        self.waveform_dir.mkdir(parents=True, exist_ok=True)
        self.peak_count = peak_count
        self.ffmpeg_path = get_ffmpeg_path()
        self.ffprobe_path = get_ffprobe_path()
    
    def generate_waveform(self, file_id: str, audio_path: str, db: Session) -> bool:
        """
        Generate waveform peaks for an audio/video file.
        
        Args:
            file_id: File UUID
            audio_path: Path to audio file (WAV preferred, but supports any FFmpeg format)
            db: Database session
            
        Returns:
            True if successful, False otherwise
        """
        file = db.query(File).filter(File.id == file_id).first()
        if not file:
            logger.error(f"File {file_id} not found in database")
            return False
        
        audio_path = Path(audio_path)
        if not audio_path.exists():
            logger.warning(f"Audio file not found: {audio_path}")
            file.waveform_state = 'FAILED'
            file.waveform_error = "Audio file not found"
            db.commit()
            return False
        
        # Set generating state
        file.waveform_state = 'GENERATING'
        db.commit()
        
        try:
            # Get audio duration first
            duration = self._get_audio_duration(audio_path)
            if duration is None or duration <= 0:
                raise Exception("Could not determine audio duration")
            
            logger.info(f"Generating waveform for {file.filename} ({duration:.2f}s)")
            
            # Extract raw audio samples and compute peaks
            peaks = self._extract_peaks(audio_path, duration)
            
            if not peaks:
                raise Exception("Failed to extract audio peaks")
            
            # Save waveform JSON
            waveform_filename = f"{file_id}.json"
            waveform_path = self.waveform_dir / waveform_filename
            
            waveform_data = {
                "peaks": peaks,
                "duration": duration,
                "sample_rate": 8000  # Our downsampled rate
            }
            
            with open(waveform_path, 'w') as f:
                json.dump(waveform_data, f)
            
            # Update database
            file.waveform_path = str(waveform_path)
            file.waveform_state = 'READY'
            file.waveform_generated_at = datetime.utcnow()
            file.waveform_error = None
            db.commit()
            
            logger.info(f"✅ Waveform generated for {file.filename} ({len(peaks)} peaks)")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error(f"Waveform generation timed out for {file.filename}")
            file.waveform_state = 'FAILED'
            file.waveform_error = "Generation timed out"
            db.commit()
            return False
            
        except Exception as e:
            logger.error(f"Waveform generation failed for {file.filename}: {e}")
            file.waveform_state = 'FAILED'
            file.waveform_error = str(e)
            db.commit()
            return False
    
    def _get_audio_duration(self, audio_path: Path) -> float | None:
        """Get audio duration in seconds using ffprobe."""
        try:
            result = subprocess.run([
                self.ffprobe_path,
                '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'json',
                str(audio_path)
            ], capture_output=True, timeout=30, text=True)
            
            if result.returncode != 0:
                logger.error(f"ffprobe failed: {result.stderr}")
                return None
            
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
            
        except Exception as e:
            logger.error(f"Failed to get audio duration: {e}")
            return None
    
    def _extract_peaks(self, audio_path: Path, duration: float) -> list[float]:
        """
        Extract normalized amplitude peaks from audio file.
        
        Uses FFmpeg to convert to raw PCM, then computes peak values
        for each time window to match target peak count.
        """
        try:
            # Convert to mono 8kHz raw PCM (small, fast to process)
            result = subprocess.run([
                self.ffmpeg_path,
                '-i', str(audio_path),
                '-ac', '1',           # Mono
                '-ar', '8000',        # 8kHz sample rate
                '-f', 's16le',        # Signed 16-bit little-endian
                '-y',                 # Overwrite
                '-'                   # Output to stdout (pipe)
            ], capture_output=True, timeout=120)
            
            if result.returncode != 0:
                logger.error(f"FFmpeg failed: {result.stderr.decode()}")
                return []
            
            raw_audio = result.stdout
            
            if len(raw_audio) < 2:
                logger.error("No audio data extracted")
                return []
            
            # Parse 16-bit samples
            sample_count = len(raw_audio) // 2
            samples = struct.unpack(f'<{sample_count}h', raw_audio)
            
            # Compute peaks by windowing
            samples_per_peak = max(1, sample_count // self.peak_count)
            peaks = []
            
            for i in range(0, sample_count, samples_per_peak):
                window = samples[i:i + samples_per_peak]
                if window:
                    # Get max absolute value in window, normalize to 0-1
                    max_val = max(abs(s) for s in window)
                    normalized = max_val / 32768.0
                    peaks.append(round(normalized, 4))
            
            # Trim to exact peak count
            if len(peaks) > self.peak_count:
                peaks = peaks[:self.peak_count]
            
            logger.debug(f"Extracted {len(peaks)} peaks from {sample_count} samples")
            return peaks
            
        except Exception as e:
            logger.error(f"Peak extraction failed: {e}", exc_info=True)
            return []


# Singleton instance initialization helper
_waveform_generator = None


def get_waveform_generator() -> WaveformGenerator | None:
    """Get the waveform generator instance."""
    return _waveform_generator


def init_waveform_generator(waveform_dir: str, **kwargs) -> WaveformGenerator:
    """
    Initialize the waveform generator.
    
    Args:
        waveform_dir: Directory for waveform files
        **kwargs: Additional configuration
        
    Returns:
        WaveformGenerator instance
    """
    global _waveform_generator
    _waveform_generator = WaveformGenerator(waveform_dir, **kwargs)
    logger.info(f"Waveform generator initialized: {waveform_dir}")
    return _waveform_generator
