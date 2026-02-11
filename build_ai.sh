#!/bin/bash
set -e  # Exit on error

# ==============================================================================
# Studio Pipeline - macOS Silicon Build Script (AI MODE)
# ==============================================================================
# Builds a complete macOS .app bundle with AI analytics features
# Includes: Whisper models, LLM models, and AI dependencies
# Target: macOS 14+ (Apple Silicon)
# ==============================================================================

# Enable AI features
export BUILD_WITH_AI=true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directories
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Build configuration
APP_NAME="StudioPipeline-AI"
BUNDLE_ID="com.studiopipeline.ai"
DIST_DIR="dist"
BUILD_DIR="build"
ICON_FILE="${PROJECT_ROOT}/icon/Custom App Icon copy_1024x1024_1024x1024.icns"

# Version management
VERSION_FILE="${PROJECT_ROOT}/VERSION"
if [ -f "${VERSION_FILE}" ]; then
    VERSION=$(cat "${VERSION_FILE}")
else
    VERSION="1.0.0"
    echo "${VERSION}" > "${VERSION_FILE}"
fi

APP_DIR="${DIST_DIR}/${APP_NAME}.app"
DMG_NAME="${APP_NAME}-${VERSION}.dmg"
BACKEND_DIR="${PROJECT_ROOT}/backend"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
PACKAGING_DIR="${PROJECT_ROOT}/packaging"
SWIFT_TOOLS_DIR="${PROJECT_ROOT}/swift_tools"
MODELS_DIR="${PROJECT_ROOT}/models"
VENV_DIR="${PROJECT_ROOT}/.venv"

# Activate virtual environment if it exists
if [ -d "${VENV_DIR}" ]; then
    print_info() { echo -e "\033[1;33m→ $1\033[0m"; }
    print_info "Activating virtual environment..."
    source "${VENV_DIR}/bin/activate"
fi

# ==============================================================================
# Helper Functions
# ==============================================================================

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

check_dependencies() {
    print_header "Checking Dependencies (AI MODE)"

    local missing_deps=0

    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 not found"
        missing_deps=1
    else
        local python_version=$(python3 --version | cut -d' ' -f2)
        print_success "Python ${python_version} found"
    fi

    # Check Node.js
    if ! command -v node &> /dev/null; then
        print_error "Node.js not found"
        missing_deps=1
    else
        local node_version=$(node --version)
        print_success "Node ${node_version} found"
    fi

    # Check npm
    if ! command -v npm &> /dev/null; then
        print_error "npm not found"
        missing_deps=1
    else
        local npm_version=$(npm --version)
        print_success "npm ${npm_version} found"
    fi

    # Check codesign
    if ! command -v codesign &> /dev/null; then
        print_error "codesign not found (install Xcode Command Line Tools)"
        missing_deps=1
    else
        print_success "codesign found"
    fi

    # Check hdiutil
    if ! command -v hdiutil &> /dev/null; then
        print_error "hdiutil not found"
        missing_deps=1
    else
        print_success "hdiutil found"
    fi

    # Check PyInstaller
    if ! python3 -c "import PyInstaller" 2>/dev/null; then
        print_info "PyInstaller not found, will install..."
        pip3 install pyinstaller
        print_success "PyInstaller installed"
    else
        print_success "PyInstaller found"
    fi

    # Check AI dependencies
    print_info "Checking AI dependencies..."
    if ! python3 -c "import mlx_whisper" 2>/dev/null; then
        print_error "mlx-whisper not found. Run: pip install -r requirements-ai.txt"
        missing_deps=1
    else
        print_success "mlx-whisper found"
    fi

    if ! python3 -c "import mlx_lm" 2>/dev/null; then
        print_error "mlx-lm not found. Run: pip install -r requirements-ai.txt"
        missing_deps=1
    else
        print_success "mlx-lm found"
    fi

    # Check AI models
    print_info "Checking AI models..."
    if [ ! -d "${MODELS_DIR}/whisper" ]; then
        print_error "Whisper models not found in ${MODELS_DIR}/whisper"
        missing_deps=1
    else
        print_success "Whisper models found"
    fi

    if [ ! -d "${MODELS_DIR}/llm" ]; then
        print_error "LLM models not found in ${MODELS_DIR}/llm"
        missing_deps=1
    else
        print_success "LLM models found"
    fi

    # Check ffmpeg binaries
    print_info "Checking ffmpeg binaries..."
    if [ ! -f "${PROJECT_ROOT}/ffmpeg_bins/ffmpeg" ]; then
        print_error "ffmpeg binary not found in ${PROJECT_ROOT}/ffmpeg_bins/"
        print_info "Download from: https://www.osxexperts.net/"
        missing_deps=1
    else
        print_success "ffmpeg binary found"
    fi

    if [ ! -f "${PROJECT_ROOT}/ffmpeg_bins/ffprobe" ]; then
        print_error "ffprobe binary not found in ${PROJECT_ROOT}/ffmpeg_bins/"
        print_info "Download from: https://www.osxexperts.net/"
        missing_deps=1
    else
        print_success "ffprobe binary found"
    fi

    if [ $missing_deps -eq 1 ]; then
        print_error "Missing dependencies. Please install them and try again."
        exit 1
    fi
}

increment_version() {
    print_header "Version Management"

    local current_version="${VERSION}"

    # Parse version (MAJOR.MINOR.PATCH)
    local major=$(echo $VERSION | cut -d. -f1)
    local minor=$(echo $VERSION | cut -d. -f2)
    local patch=$(echo $VERSION | cut -d. -f3)

    # Increment patch version
    patch=$((patch + 1))

    # Update version
    VERSION="${major}.${minor}.${patch}"
    DMG_NAME="${APP_NAME}-${VERSION}.dmg"

    # Save new version
    echo "${VERSION}" > "${VERSION_FILE}"

    print_info "Version: ${current_version} → ${VERSION}"
    print_success "Version incremented"
}

clean_build() {
    print_header "Cleaning Previous Builds (AI MODE)"

    # Create dist directory if it doesn't exist
    mkdir -p "${DIST_DIR}"

    # Remove .app bundle (always rebuilt)
    if [ -d "${APP_DIR}" ]; then
        print_info "Removing ${APP_DIR}"
        rm -rf "${APP_DIR}"
    fi

    # Remove backend directory (PyInstaller output)
    if [ -d "${DIST_DIR}/backend" ]; then
        print_info "Removing ${DIST_DIR}/backend"
        rm -rf "${DIST_DIR}/backend"
    fi

    # Keep previous DMG files (they have version numbers)
    local dmg_count=$(ls -1 "${DIST_DIR}"/*-AI-*.dmg 2>/dev/null | wc -l)
    if [ $dmg_count -gt 0 ]; then
        print_info "Keeping ${dmg_count} previous AI DMG file(s)"
    fi

    # Remove build directory
    if [ -d "${BUILD_DIR}" ]; then
        print_info "Removing ${BUILD_DIR}"
        rm -rf "${BUILD_DIR}"
    fi

    # Remove PyInstaller spec
    if [ -f "${APP_NAME}.spec" ]; then
        print_info "Removing ${APP_NAME}.spec"
        rm -f "${APP_NAME}.spec"
    fi

    print_success "Clean complete"
}

build_menu_bar_app() {
    print_header "Building Menu Bar App"

    local swift_source="${PROJECT_ROOT}/MenuBarApp/main.swift"
    local swift_output="${BUILD_DIR}/MenuBarApp/StudioPipeline"

    if [ ! -f "${swift_source}" ]; then
        print_error "Swift source not found: ${swift_source}"
        exit 1
    fi

    mkdir -p "${BUILD_DIR}/MenuBarApp"

    print_info "Compiling Swift menu bar app..."
    swiftc -O -whole-module-optimization \
        -target arm64-apple-macos14.0 \
        "${swift_source}" \
        -o "${swift_output}"

    if [ ! -f "${swift_output}" ]; then
        print_error "Swift compilation failed"
        exit 1
    fi

    print_success "Menu bar app compiled successfully"
}

build_frontend() {
    print_header "Building Frontend"

    cd "${FRONTEND_DIR}"

    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        print_info "Installing npm dependencies..."
        npm install
    fi

    # Build production bundle with version and AI mode
    print_info "Building React app with Vite..."
    VITE_APP_VERSION="${VERSION}" VITE_APP_AI_ENABLED="true" npm run build

    if [ ! -d "dist" ]; then
        print_error "Frontend build failed - dist directory not created"
        exit 1
    fi

    cd "${PROJECT_ROOT}"
    print_success "Frontend built successfully"
}

create_pyinstaller_spec() {
    print_header "Creating PyInstaller Spec File (AI MODE)"

    cat > "${APP_NAME}.spec" << 'EOF'
# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, collect_all, collect_submodules
import os

def add_directory(dir_path: Path, target: str):
    """Recursively enumerate files in a directory for PyInstaller datas.
    Follows symlinks and preserves subdirectory structure under target."""
    entries = []
    if not dir_path.exists():
        return entries
    for root, dirs, files in os.walk(dir_path, followlinks=True):
        root_path = Path(root)
        try:
            rel = root_path.relative_to(dir_path)
        except ValueError:
            rel = Path('.')
        for f in files:
            src = root_path / f
            if rel == Path('.'):
                dest = target
            else:
                dest = f"{target}/{rel}".rstrip('/')
            entries.append((str(src), dest))
    return entries

block_cipher = None

# Paths
project_root = Path.cwd()
backend_dir = project_root / 'backend'
frontend_dist = project_root / 'frontend' / 'dist'
swift_tools = project_root / 'swift_tools'
models_dir = project_root / 'models'

datas = []
extra_binaries = []
extra_imports = []

# Collect all internal application packages
# These are needed because some modules are dynamically imported at runtime
# (e.g., ftp_deletion_service imported inside deletion_cleanup_loop)
# and PyInstaller cannot trace them through static analysis
app_hiddenimports = (
    collect_submodules('services') +
    collect_submodules('api') +
    collect_submodules('workers') +
    collect_submodules('repositories') +
    collect_submodules('utils') +
    collect_submodules('domain') +
    collect_submodules('dtos') +
    collect_submodules('config')
)

# Frontend build (preserve directory structure)
datas += add_directory(frontend_dist, 'frontend')

# Single denoiser ONNX model
denoiser = models_dir / 'denoiser_model.onnx'
if denoiser.exists():
    datas.append((str(denoiser), 'models'))

# Whisper models (recursive)
datas += add_directory(models_dir / 'whisper', 'models/whisper')

# LLM models (recursive)
datas += add_directory(models_dir / 'llm', 'models/llm')

# Metadata for required packages
datas += copy_metadata('aioftp')
datas += copy_metadata('fastapi')
datas += copy_metadata('pydantic')
datas += copy_metadata('uvicorn')
datas += copy_metadata('mlx-whisper')
datas += copy_metadata('mlx-lm')
datas += copy_metadata('mlx-vlm')
datas += copy_metadata('transformers')

# Collect all MLX resources (binaries and hidden imports)
# This is critical for mlx-whisper and mlx-vlm (vision) to work on customer machines
for pkg in ['mlx', 'mlx_whisper', 'mlx_lm', 'mlx_vlm']:
    try:
        tmp_ret = collect_all(pkg)
        datas += tmp_ret[0]
        extra_binaries += tmp_ret[1]
        extra_imports += tmp_ret[2]
    except Exception as e:
        print(f"Warning: Could not collect {pkg}: {e}")

a = Analysis(
    [str(backend_dir / 'main.py')],
    pathex=[str(backend_dir)],
    binaries=[
        (str(swift_tools / 'boost'), 'swift_tools'),
        (str(swift_tools / 'convert'), 'swift_tools'),
        (str(swift_tools / 'extract'), 'swift_tools'),
        (str(swift_tools / 'mp3converter'), 'swift_tools'),
        (str(swift_tools / 'remux'), 'swift_tools'),
        (str(swift_tools / 'split'), 'swift_tools'),
        (str(swift_tools / 'lame'), 'swift_tools'),
        # FFmpeg binaries for transcription and metadata extraction
        (str(project_root / 'ffmpeg_bins' / 'ffmpeg'), 'ffmpeg_bins'),
        (str(project_root / 'ffmpeg_bins' / 'ffprobe'), 'ffmpeg_bins'),
    ] + extra_binaries,
    datas=datas,
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'websockets',
        'onnxruntime',
        'numpy',
        'soundfile',
        'librosa',
        'keyring',
        'keyring.backends',
        'keyring.backends.macOS',
        'mlx',
        'mlx_whisper',
        'mlx_lm',
        'mlx_vlm',
        'mlx_vlm.models',
        'mlx_vlm.models.qwen3_vl',
        'mlx_vlm.models.base',
        'mlx_vlm.prompt_utils',
        'mlx_vlm.utils',
        'transformers',
        'tokenizers',
        'torch',
        'safetensors',
        'huggingface_hub',
        'openpyxl',
        'migrate_add_queue_order',
    ] + extra_imports + app_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'PIL.ImageQt',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64',
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='backend',
)
EOF

    print_success "PyInstaller spec created with AI models"
}

build_backend() {
    print_header "Building Backend with PyInstaller (AI MODE)"

    print_info "Running PyInstaller (this may take several minutes with AI models)..."
    python3 -m PyInstaller \
        --noconfirm \
        "${APP_NAME}.spec"

    if [ ! -d "${DIST_DIR}/backend" ]; then
        print_error "Backend build failed - backend directory not created"
        exit 1
    fi

    # Make Swift tools executable (PyInstaller puts them in _internal)
    print_info "Setting executable permissions on Swift tools..."
    if [ -d "${DIST_DIR}/backend/_internal/swift_tools" ]; then
        chmod +x "${DIST_DIR}/backend/_internal/swift_tools/"*
        print_success "Swift tools permissions set"
    else
        print_error "Swift tools directory not found"
        exit 1
    fi

    # Verify AI models were packaged
    print_info "Verifying AI models were packaged..."
    if [ -d "${DIST_DIR}/backend/_internal/models/whisper" ]; then
        print_success "Whisper models packaged"
    else
        print_error "Whisper models not found in package"
        exit 1
    fi

    if [ -d "${DIST_DIR}/backend/_internal/models/llm" ]; then
        print_success "LLM models packaged"
    else
        print_error "LLM models not found in package"
        exit 1
    fi

    # Verify ffmpeg binaries were packaged
    print_info "Verifying ffmpeg binaries were packaged..."
    if [ -f "${DIST_DIR}/backend/_internal/ffmpeg_bins/ffmpeg" ]; then
        chmod +x "${DIST_DIR}/backend/_internal/ffmpeg_bins/ffmpeg"
        print_success "ffmpeg binary packaged"
    else
        print_error "ffmpeg binary not found in package"
        exit 1
    fi

    if [ -f "${DIST_DIR}/backend/_internal/ffmpeg_bins/ffprobe" ]; then
        chmod +x "${DIST_DIR}/backend/_internal/ffmpeg_bins/ffprobe"
        print_success "ffprobe binary packaged"
    else
        print_error "ffprobe binary not found in package"
        exit 1
    fi

    print_success "Backend built successfully with AI models"
}

create_app_bundle() {
    print_header "Creating macOS App Bundle (AI MODE)"

    # Create app bundle structure
    print_info "Creating app bundle structure..."
    mkdir -p "${APP_DIR}/Contents/MacOS"
    mkdir -p "${APP_DIR}/Contents/Resources"
    mkdir -p "${APP_DIR}/Contents/Frameworks"

    # Copy backend
    print_info "Copying backend..."
    cp -R "${DIST_DIR}/backend" "${APP_DIR}/Contents/MacOS/"

    # Copy Swift menu bar app as main executable
    print_info "Copying menu bar app..."
    cp "${BUILD_DIR}/MenuBarApp/StudioPipeline" "${APP_DIR}/Contents/MacOS/${APP_NAME}"
    chmod +x "${APP_DIR}/Contents/MacOS/${APP_NAME}"

    # Create Info.plist (use template or create one)
    print_info "Creating Info.plist..."
    if [ -f "${PACKAGING_DIR}/Info.plist.template" ]; then
        sed -e "s/{{APP_NAME}}/${APP_NAME}/g" \
            -e "s/{{BUNDLE_ID}}/${BUNDLE_ID}/g" \
            -e "s/{{VERSION}}/${VERSION}/g" \
            "${PACKAGING_DIR}/Info.plist.template" > "${APP_DIR}/Contents/Info.plist"
    else
        # Create basic Info.plist
        cat > "${APP_DIR}/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>${BUNDLE_ID}</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
PLIST
    fi

    # Create PkgInfo
    echo -n "APPL????" > "${APP_DIR}/Contents/PkgInfo"

    # Copy icon
    if [ -f "${ICON_FILE}" ]; then
        print_info "Copying app icon..."
        cp "${ICON_FILE}" "${APP_DIR}/Contents/Resources/AppIcon.icns"
    else
        print_error "Icon file not found: ${ICON_FILE}"
        # Don't exit, just warn
    fi

    print_success "App bundle created with AI features"
}

sign_app() {
    print_header "Code Signing (Ad-hoc, AI MODE)"

    print_info "Signing Swift tools..."
    for tool in "${APP_DIR}/Contents/MacOS/backend/_internal/swift_tools/"*; do
        codesign -s - --force "$tool" 2>/dev/null || true
    done

    print_info "Signing backend executable..."
    codesign -s - --force "${APP_DIR}/Contents/MacOS/backend/backend" 2>/dev/null || true

    print_info "Signing app bundle (may show warnings for dist-info files)..."
    codesign -s - --force "${APP_DIR}" 2>&1 | grep -v "unsuitable" || true

    # Note: Full verification will fail due to PyInstaller dist-info files, but the app will still run
    print_success "Code signing completed (app is runnable with AI features)"
}

create_dmg() {
    print_header "Creating DMG Installer"

    local dmg_temp_dir="${BUILD_DIR}/dmg"
    local dmg_path="${DIST_DIR}/${DMG_NAME}"

    # Remove existing DMG
    if [ -f "${dmg_path}" ]; then
        rm -f "${dmg_path}"
    fi

    # Create staging directory
    print_info "Creating DMG staging directory..."
    mkdir -p "${dmg_temp_dir}"

    # Copy app
    print_info "Copying app to staging..."
    cp -R "${APP_DIR}" "${dmg_temp_dir}/"

    # Create Applications symlink
    print_info "Creating Applications symlink..."
    ln -s /Applications "${dmg_temp_dir}/Applications"

    # Create DMG
    print_info "Creating disk image (this will be large due to AI models)..."
    hdiutil create \
        -volname "${APP_NAME}" \
        -srcfolder "${dmg_temp_dir}" \
        -ov \
        -format UDZO \
        "${dmg_path}"

    # Clean up staging
    rm -rf "${dmg_temp_dir}"

    # Get DMG size
    local dmg_size=$(du -h "${dmg_path}" | cut -f1)
    print_success "DMG created: ${dmg_path} (${dmg_size})"
}

print_summary() {
    print_header "Build Complete! (AI MODE)"

    echo ""
    echo -e "${GREEN}Built artifacts with AI features:${NC}"
    echo -e "  ${BLUE}App Bundle:${NC} ${APP_DIR}"
    echo -e "  ${BLUE}DMG Installer:${NC} ${DIST_DIR}/${DMG_NAME}"
    echo ""

    if [ -d "${APP_DIR}" ]; then
        local app_size=$(du -sh "${APP_DIR}" | cut -f1)
        echo -e "${GREEN}App Bundle Size:${NC} ${app_size}"
    fi

    if [ -f "${DIST_DIR}/${DMG_NAME}" ]; then
        local dmg_size=$(du -sh "${DIST_DIR}/${DMG_NAME}" | cut -f1)
        echo -e "${GREEN}DMG Size:${NC} ${dmg_size}"
    fi

    echo ""
    echo -e "${GREEN}AI Features Included:${NC}"
    echo -e "  ${BLUE}• Whisper Transcription${NC}"
    echo -e "  ${BLUE}• LLM Content Analysis${NC}"
    echo -e "  ${BLUE}• Excel Export${NC}"
    echo -e "  ${BLUE}• Scheduled Processing${NC}"
    echo ""
    echo -e "${YELLOW}To test the app:${NC}"
    echo -e "  open ${APP_DIR}"
    echo ""
    echo -e "${YELLOW}To install:${NC}"
    echo -e "  open ${DIST_DIR}/${DMG_NAME}"
    echo -e "  Drag ${APP_NAME}.app to Applications folder"
    echo ""
}

# ==============================================================================
# Main Build Process
# ==============================================================================

main() {
    print_header "Studio Pipeline - macOS Build Script (AI MODE)"
    echo -e "${BLUE}Building ${APP_NAME} v${VERSION} with AI Analytics${NC}"
    echo -e "${BLUE}For Apple Silicon with AI Models${NC}"
    echo ""

    # Run build steps
    check_dependencies
    increment_version
    clean_build
    build_menu_bar_app
    build_frontend
    create_pyinstaller_spec
    build_backend
    create_app_bundle
    sign_app
    create_dmg
    print_summary
}

# Run main
main "$@"
