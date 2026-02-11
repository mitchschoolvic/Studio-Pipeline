#!/bin/bash
set -e  # Exit on error

# ==============================================================================
# Studio Pipeline - macOS Silicon Build Script
# ==============================================================================
# Builds a complete macOS .app bundle and .dmg installer with ad-hoc signing
# Target: macOS 14+ (Apple Silicon)
# ==============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directories
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Build configuration
APP_NAME="StudioPipeline"
BUNDLE_ID="com.studiopipeline.app"
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
VENV_DIR="${PROJECT_ROOT}/venv"

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
    print_header "Checking Dependencies"

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

    # Check ffmpeg binaries
    print_info "Checking ffmpeg binaries..."
    if [ ! -f "${PROJECT_ROOT}/ffmpeg_bins/ffmpeg" ]; then
        print_error "ffmpeg binary not found in ${PROJECT_ROOT}/ffmpeg_bins/"
        print_info "Download from: https://evermeet.cx/ffmpeg/"
        missing_deps=1
    else
        print_success "ffmpeg binary found"
    fi

    if [ ! -f "${PROJECT_ROOT}/ffmpeg_bins/ffprobe" ]; then
        print_error "ffprobe binary not found in ${PROJECT_ROOT}/ffmpeg_bins/"
        print_info "Download from: https://evermeet.cx/ffmpeg/"
        missing_deps=1
    else
        print_success "ffprobe binary found"
    fi

    if [ $missing_deps -eq 1 ]; then
        print_error "Missing dependencies. Please install them and try again."
        exit 1
    fi

    # Install/Update Python dependencies (standard build - no AI)
    print_info "Installing/Updating Python dependencies..."
    pip3 install -r "${PROJECT_ROOT}/requirements.txt"
    pip3 install -e "${PROJECT_ROOT}/backend/"
    
    print_success "Dependencies installed"
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
    print_header "Cleaning Previous Builds"

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
    local dmg_count=$(ls -1 "${DIST_DIR}"/*.dmg 2>/dev/null | wc -l)
    if [ $dmg_count -gt 0 ]; then
        print_info "Keeping ${dmg_count} previous DMG file(s)"
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

    # Build production bundle with version
    print_info "Building React app with Vite..."
    VITE_APP_VERSION="${VERSION}" npm run build

    if [ ! -d "dist" ]; then
        print_error "Frontend build failed - dist directory not created"
        exit 1
    fi

    cd "${PROJECT_ROOT}"
    print_success "Frontend built successfully"
}

create_pyinstaller_spec() {
    print_header "Creating PyInstaller Spec File (Standard Build)"

    cat > "${APP_NAME}.spec" << 'EOF'
# -*- mode: python ; coding: utf-8 -*-
# Standard Build - No AI/LLM features

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, collect_submodules, collect_all

block_cipher = None

# Collect all mediapipe submodules and data
mediapipe_datas, mediapipe_binaries, mediapipe_hiddenimports = collect_all('mediapipe')

# Paths
project_root = Path.cwd()
backend_dir = project_root / 'backend'
frontend_dist = project_root / 'frontend' / 'dist'
swift_tools = project_root / 'swift_tools'
models_dir = project_root / 'models'

a = Analysis(
    [str(backend_dir / 'main.py')],
    pathex=[str(backend_dir)],
    binaries=[
        # Swift tools (already compiled for ARM64)
        (str(swift_tools / 'boost'), 'swift_tools'),
        (str(swift_tools / 'convert'), 'swift_tools'),
        (str(swift_tools / 'extract'), 'swift_tools'),
        (str(swift_tools / 'mp3converter'), 'swift_tools'),
        (str(swift_tools / 'remux'), 'swift_tools'),
        (str(swift_tools / 'split'), 'swift_tools'),
        (str(swift_tools / 'gesturetrim'), 'swift_tools'),
        # External tools
        (str(swift_tools / 'lame'), 'swift_tools'),
        # FFmpeg binaries for metadata extraction and thumbnail generation
        (str(project_root / 'ffmpeg_bins' / 'ffmpeg'), 'ffmpeg_bins'),
        (str(project_root / 'ffmpeg_bins' / 'ffprobe'), 'ffmpeg_bins'),
    ] + mediapipe_binaries,
    datas=[
        # Frontend build
        (str(frontend_dist), 'frontend'),
        # ONNX denoiser model (neural net audio enhancement - NOT AI/LLM)
        (str(models_dir / 'denoiser_model.onnx'), 'models'),
        # MediaPipe hand landmarker model (gesture detection)
        (str(models_dir / 'hand_landmarker.task'), 'models'),
    ] + copy_metadata('aioftp') + copy_metadata('fastapi') + copy_metadata('pydantic') + copy_metadata('uvicorn') + mediapipe_datas,
    hiddenimports=[
        # Uvicorn server
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
        # Audio processing (denoiser)
        'onnxruntime',
        'numpy',
        'soundfile',
        'librosa',
        # Gesture detection (video trimming)
        'mediapipe',
        'mediapipe.tasks',
        'mediapipe.tasks.cc',
        'mediapipe.tasks.cc.vision',
        'mediapipe.tasks.cc.vision.hand_landmarker',
        'mediapipe.tasks.python',
        'mediapipe.tasks.python.core',
        'mediapipe.tasks.python.vision',
        'mediapipe.tasks.python.vision.core',
        'mediapipe.python',
        'mediapipe.python._framework_bindings',
        'cv2',
        # Matplotlib (required by mediapipe)
        'matplotlib',
        'matplotlib.pyplot',
        'matplotlib.backends',
        # System integration
        'keyring',
        'keyring.backends',
        'keyring.backends.macOS',
        # Database migration
        'migrate_add_queue_order',
    ] + mediapipe_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # GUI frameworks not used
        'tkinter',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'PIL.ImageQt',
        # AI/LLM packages (not included in standard build)
        'mlx',
        'mlx_whisper',
        'mlx_lm',
        'mlx_vlm',
        'transformers',
        'torch',
        'huggingface_hub',
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

    print_success "PyInstaller spec created"
}

build_backend() {
    print_header "Building Backend with PyInstaller (Standard Build)"

    print_info "Running PyInstaller (this may take several minutes)..."
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

    # Verify and set permissions on ffmpeg binaries
    print_info "Verifying ffmpeg binaries..."
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

    print_success "Backend built successfully"
}

create_app_bundle() {
    print_header "Creating macOS App Bundle"

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

    # Create Info.plist
    print_info "Creating Info.plist..."
    sed -e "s/{{APP_NAME}}/${APP_NAME}/g" \
        -e "s/{{BUNDLE_ID}}/${BUNDLE_ID}/g" \
        -e "s/{{VERSION}}/${VERSION}/g" \
        "${PACKAGING_DIR}/Info.plist.template" > "${APP_DIR}/Contents/Info.plist"

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

    print_success "App bundle created"
}

sign_app() {
    print_header "Code Signing (Ad-hoc)"

    print_info "Signing Swift tools..."
    for tool in "${APP_DIR}/Contents/MacOS/backend/_internal/swift_tools/"*; do
        codesign -s - --force "$tool" 2>/dev/null || true
    done

    print_info "Signing backend executable..."
    codesign -s - --force "${APP_DIR}/Contents/MacOS/backend/backend" 2>/dev/null || true

    print_info "Signing app bundle (may show warnings for dist-info files)..."
    codesign -s - --force "${APP_DIR}" 2>&1 | grep -v "unsuitable" || true

    # Note: Full verification will fail due to PyInstaller dist-info files, but the app will still run
    print_success "Code signing completed (app is runnable)"
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
    print_info "Creating disk image..."
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
    print_header "Build Complete!"

    echo ""
    echo -e "${GREEN}Built artifacts:${NC}"
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
    print_header "Studio Pipeline - macOS Build Script"
    echo -e "${BLUE}Building ${APP_NAME} v${VERSION} for Apple Silicon${NC}"
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
