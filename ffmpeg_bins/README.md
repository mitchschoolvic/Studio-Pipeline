# FFmpeg Binaries

This directory contains native Apple Silicon (arm64) ffmpeg binaries bundled with the application.

## Required Binaries

- `ffmpeg` - Audio/video processing (used by mlx-whisper)
- `ffprobe` - Metadata extraction (used by video_metadata.py)

## Download Instructions

Download the latest arm64 binaries from [osxexperts.net](https://www.osxexperts.net/):

```bash
# Download ffmpeg (arm64)
curl -L https://www.osxexperts.net/ffmpeg80arm.zip -o /tmp/ffmpeg.zip
unzip /tmp/ffmpeg.zip -d ffmpeg_bins/

# Download ffprobe (arm64)
curl -L https://www.osxexperts.net/ffprobe80arm.zip -o /tmp/ffprobe.zip
unzip /tmp/ffprobe.zip -d ffmpeg_bins/

# Make executable
chmod +x ffmpeg_bins/ffmpeg ffmpeg_bins/ffprobe

# Verify architecture (should show arm64)
file ffmpeg_bins/ffmpeg
file ffmpeg_bins/ffprobe
```

## Why These Binaries?

- **Native Performance**: Compiled for Apple Silicon (arm64)
- **No Dependencies**: Static binaries, no external libraries needed
- **Bundled with App**: Ensures transcription works on customer machines without installing ffmpeg
- **Version Control**: Exact ffmpeg version shipped with application

## Usage

The `backend/utils/ffmpeg_helper.py` module automatically locates these binaries at runtime, whether running in development or as a PyInstaller bundle.
