# ML Models Directory

This directory contains the machine learning models used by Studio Pipeline's AI features.

⚠️ **Large models are not included in the repository.** Download them using the provided script or manual instructions below.

## Quick Start

Run the download script to get all AI models at once:

```bash
cd models
./download_models.sh
```

This will download all three required models (~1.1 GB total).

---

## Required Models

### For Standard Build (Audio Processing)
- **denoiser_model.onnx** (108 KB) - Neural network audio denoiser
  - ✅ Included in the repository

### For AI Build (Transcription & Analytics)

**Total size: ~1.1 GB** (excluded from git repository)

#### 1. Whisper Model (Transcription)
- **Size**: ~459 MB
- **Location**: `models/whisper/mlx-community-whisper-small-mlx/`
- **Download**:
```bash
python -m mlx_whisper.load_models --model mlx-community/whisper-small-mlx
```

#### 2. Qwen3-VL Model (Vision-Language Analysis)
- **Size**: ~608 MB (8-bit quantized)
- **Location**: `models/llm/Qwen3-VL-4B-Instruct-MLX-8bit/`
- **Download**:
```bash
pip install huggingface-hub
python -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/Qwen2.5-VL-7B-Instruct-8bit', local_dir='models/llm/Qwen3-VL-4B-Instruct-MLX-8bit')"
```

#### 3. MediaPipe Hand Landmarker (Gesture Detection)
- **Size**: ~13 MB
- **Location**: `models/hand_landmarker.task`
- **Download**:
```bash
curl -L -o models/hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
```

## Directory Structure

```
models/
├── README.md (this file)
├── denoiser_model.onnx          # Included
├── hand_landmarker.task         # Download required
├── llm/
│   └── Qwen3-VL-4B-Instruct-MLX-8bit/  # Download required
│       ├── model.safetensors
│       ├── config.json
│       └── ...
└── whisper/
    └── mlx-community-whisper-small-mlx/  # Download required
        ├── weights.npz
        ├── config.json
        └── ...
```

## Notes

- Models are excluded from git due to their large size (multi-GB)
- Standard build works without AI models
- AI features require all three additional models
- Models are optimized for Apple Silicon (MLX framework)
