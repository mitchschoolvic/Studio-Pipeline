#!/bin/bash
# Download ML Models for Studio Pipeline AI Features
# Run this script to download all required models for AI transcription and analytics

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MODELS_DIR="${SCRIPT_DIR}"

echo "=================================================="
echo "Studio Pipeline - AI Models Downloader"
echo "=================================================="
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not found"
    exit 1
fi

# Check if pip packages are installed
echo "→ Checking dependencies..."
python3 -c "import mlx" 2>/dev/null || {
    echo "❌ mlx-whisper not installed. Run: pip install mlx-whisper"
    exit 1
}

# 1. Download Whisper Model
echo ""
echo "→ Downloading Whisper model (MLX-optimized, ~459 MB)..."
if [ ! -f "${MODELS_DIR}/whisper/mlx-community-whisper-small-mlx/weights.npz" ]; then
    python3 -m mlx_whisper.load_models --model mlx-community/whisper-small-mlx
    # Move to correct location if needed
    if [ -d "${HOME}/.cache/huggingface/hub/models--mlx-community--whisper-small-mlx" ]; then
        echo "→ Moving model to ${MODELS_DIR}/whisper/"
        mkdir -p "${MODELS_DIR}/whisper"
        cp -r "${HOME}/.cache/huggingface/hub/models--mlx-community--whisper-small-mlx/snapshots/"*/* "${MODELS_DIR}/whisper/mlx-community-whisper-small-mlx/"
    fi
    echo "✅ Whisper model downloaded"
else
    echo "✅ Whisper model already exists"
fi

# 2. Download Qwen3-VL Model
echo ""
echo "→ Downloading Qwen3-VL model (8-bit quantized, ~608 MB)..."
if [ ! -f "${MODELS_DIR}/llm/Qwen3-VL-4B-Instruct-MLX-8bit/model.safetensors" ]; then
    python3 << 'PYTHON'
from huggingface_hub import snapshot_download
import os

models_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(models_dir, "llm/Qwen3-VL-4B-Instruct-MLX-8bit")

print(f"Downloading to: {output_dir}")
snapshot_download(
    "mlx-community/Qwen2.5-VL-7B-Instruct-8bit",
    local_dir=output_dir,
    local_dir_use_symlinks=False
)
PYTHON
    echo "✅ Qwen3-VL model downloaded"
else
    echo "✅ Qwen3-VL model already exists"
fi

# 3. Download MediaPipe Hand Landmarker
echo ""
echo "→ Downloading MediaPipe Hand Landmarker (~13 MB)..."
if [ ! -f "${MODELS_DIR}/hand_landmarker.task" ]; then
    curl -L -o "${MODELS_DIR}/hand_landmarker.task" \
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    echo "✅ Hand Landmarker downloaded"
else
    echo "✅ Hand Landmarker already exists"
fi

echo ""
echo "=================================================="
echo "✅ All AI models downloaded successfully!"
echo "=================================================="
echo ""
echo "Models location:"
echo "  - Whisper:        ${MODELS_DIR}/whisper/mlx-community-whisper-small-mlx/"
echo "  - Qwen3-VL:       ${MODELS_DIR}/llm/Qwen3-VL-4B-Instruct-MLX-8bit/"
echo "  - Hand Landmarker: ${MODELS_DIR}/hand_landmarker.task"
echo ""
echo "Total size: ~1.1 GB"
echo ""
echo "You can now build with AI features: BUILD_WITH_AI=true ./build.sh"
echo ""
