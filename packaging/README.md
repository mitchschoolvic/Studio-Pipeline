# Studio Pipeline - macOS Packaging Guide

This directory contains scripts and templates for building Studio Pipeline as a native macOS application for Apple Silicon.

## Quick Start

From the project root, run:

```bash
./build.sh
```

This will create:
- `dist/StudioPipeline.app` - The macOS application bundle
- `dist/StudioPipeline.dmg` - The DMG installer

## Build Process Overview

The `build.sh` script performs the following steps:

1. **Check Dependencies** - Verifies Python, Node.js, PyInstaller, codesign, and hdiutil are available
2. **Clean Build** - Removes previous build artifacts
3. **Build Frontend** - Runs `npm run build` to create production React bundle
4. **Create PyInstaller Spec** - Generates PyInstaller configuration with all resources
5. **Build Backend** - Uses PyInstaller to bundle Python backend + dependencies
6. **Create App Bundle** - Assembles macOS `.app` structure with launcher script
7. **Code Sign** - Ad-hoc signs the app bundle (for development/testing)
8. **Create DMG** - Generates disk image installer with Applications symlink

## Prerequisites

### Required Tools

- **Python 3.12+** with pip
- **Node.js 18+** with npm
- **PyInstaller 6.0+** (`pip install pyinstaller`)
- **Xcode Command Line Tools** (`xcode-select --install`)

### Verify Dependencies

```bash
python3 --version
node --version
npm --version
python3 -m PyInstaller --version
codesign --version
hdiutil -version
```

## File Structure

```
packaging/
├── README.md              # This file
├── launcher.sh            # App startup script (embedded in .app)
└── Info.plist.template    # macOS bundle metadata with entitlements
```

## Files Created by Build

### StudioPipeline.app Structure

```
StudioPipeline.app/
├── Contents/
│   ├── Info.plist                    # Bundle metadata
│   ├── PkgInfo                       # Bundle type identifier
│   ├── MacOS/
│   │   ├── StudioPipeline            # Launcher script (bash)
│   │   └── backend/                  # PyInstaller bundle
│   │       ├── backend               # Python executable
│   │       ├── _internal/            # Python libraries
│   │       ├── swift_tools/          # Audio/video tools
│   │       │   ├── boost
│   │       │   ├── convert
│   │       │   ├── extract
│   │       │   ├── remux
│   │       │   └── split
│   │       ├── models/
│   │       │   └── denoiser_model.onnx
│   │       └── frontend/             # React build
│   │           ├── index.html
│   │           └── assets/
│   ├── Resources/                    # (future: icons, etc.)
│   └── Frameworks/                   # (if needed)
```

## Launcher Script Behavior

The `launcher.sh` script (embedded as `StudioPipeline` in `MacOS/`):

1. **Checks for existing server** on port 8000
2. **Starts backend** as background process
3. **Waits for health check** (up to 30 seconds)
4. **Opens browser** to `http://localhost:8000`
5. **Monitors backend** and shows error dialogs if it crashes
6. **Handles cleanup** on Ctrl+C or app quit

### Logs

Application logs are written to:
```
~/Library/Logs/StudioPipeline/app.log
```

Backend PID file:
```
~/Library/Logs/StudioPipeline/backend.pid
```

## Entitlements

The `Info.plist.template` includes entitlements for:

### Network Access
- `com.apple.security.network.server` - FastAPI server
- `com.apple.security.network.client` - FTP client

### File System Access
- `com.apple.security.files.user-selected.read-write` - User-selected files
- `com.apple.security.files.downloads.read-write` - Downloads folder
- Absolute path exceptions for `/tmp/`, `~/Library/Application Support/`, `~/Videos/`

### Python Runtime
- `com.apple.security.cs.allow-jit` - JIT compilation
- `com.apple.security.cs.allow-unsigned-executable-memory` - NumPy/ONNX
- `com.apple.security.cs.allow-dyld-environment-variables` - Dynamic linking
- `com.apple.security.cs.disable-library-validation` - Python extensions

### Process Management
- `com.apple.security.inherit` - Child process inheritance

## Code Signing

### Ad-hoc Signing (Development)

The build script uses ad-hoc signing by default:

```bash
codesign -s - --force --deep --preserve-metadata=entitlements StudioPipeline.app
```

This allows:
- ✅ Running on your local Mac
- ✅ Testing all functionality
- ❌ Distribution to other Macs (will require Developer ID)

### Developer ID Signing (Distribution)

To sign for distribution, modify `build.sh` and replace:

```bash
codesign -s - --force --deep ...
```

With:

```bash
codesign -s "Developer ID Application: Your Name (TEAM_ID)" --force --deep \
  --options runtime \
  --entitlements entitlements.plist \
  StudioPipeline.app
```

Then notarize:

```bash
# Create zip for notarization
ditto -c -k --keepParent StudioPipeline.app StudioPipeline.zip

# Submit for notarization
xcrun notarytool submit StudioPipeline.zip \
  --apple-id "your@email.com" \
  --password "@keychain:AC_PASSWORD" \
  --team-id "TEAM_ID" \
  --wait

# Staple ticket
xcrun stapler staple StudioPipeline.app
```

## PyInstaller Configuration

The build script dynamically creates `StudioPipeline.spec` with:

### Included Binaries
- Swift tools from `swift_tools/` → `swift_tools/`
- ONNX model from `models/` → `models/`

### Included Data
- Frontend build from `frontend/dist/` → `frontend/`

### Hidden Imports
- `uvicorn.logging`, `uvicorn.loops.*`, `uvicorn.protocols.*`
- `websockets`
- `onnxruntime`, `numpy`, `soundfile`, `librosa`
- `keyring`, `keyring.backends.macOS`

### Excluded Modules
- `tkinter`, `matplotlib`, `PyQt5`, `PyQt6`, `PySide2`, `PySide6`
- `PIL.ImageQt`

### Target Architecture
- `arm64` (Apple Silicon native)

## Testing the Build

### 1. Test the .app directly

```bash
open dist/StudioPipeline.app
```

The app should:
- Launch without errors
- Start the backend server
- Open your browser to the frontend
- Show the Studio Pipeline dashboard

### 2. Test the DMG installer

```bash
open dist/StudioPipeline.dmg
```

- Drag `StudioPipeline.app` to the `Applications` folder
- Eject the DMG
- Launch from `Applications/StudioPipeline.app`

### 3. Verify functionality

- **FTP Connection**: Test discovery scan
- **File Copy**: Download a test video
- **Processing**: Verify Swift tools execute
- **Output**: Check organized files in `~/Videos/StudioPipeline/`
- **Database**: Verify SQLite database at `~/Library/Application Support/StudioPipeline/pipeline.db`

### 4. Check logs

```bash
tail -f ~/Library/Logs/StudioPipeline/app.log
```

## Troubleshooting

### Build fails with "PyInstaller not found"

```bash
pip3 install pyinstaller
```

### Build fails with "npm not found"

```bash
brew install node
```

### App won't launch: "Cannot be opened because the developer cannot be verified"

Right-click the app, select "Open", then click "Open" in the dialog.

Or disable Gatekeeper temporarily:

```bash
sudo spctl --master-disable
# Open the app
sudo spctl --master-enable
```

### Backend fails to start: "Port 8000 already in use"

Kill any existing processes on port 8000:

```bash
lsof -ti:8000 | xargs kill -9
```

### Swift tools not executable

Manually fix permissions:

```bash
chmod +x dist/StudioPipeline.app/Contents/MacOS/backend/swift_tools/*
```

### Frontend not loading

Check that frontend was built:

```bash
ls -la frontend/dist/
```

Rebuild if needed:

```bash
cd frontend && npm run build
```

### "Killed: 9" when launching

This usually means code signing failed. Re-sign the app:

```bash
codesign -s - --force --deep dist/StudioPipeline.app
```

## DMG Customization

The build script creates a basic DMG. To customize:

### Add Background Image

1. Create a 600x400 PNG background
2. Save as `packaging/dmg-background.png`
3. Modify the `create_dmg()` function in `build.sh`

### Change Window Size/Position

Edit the `create_dmg()` function:

```bash
hdiutil create \
  -volname "${APP_NAME}" \
  -srcfolder "${dmg_temp_dir}" \
  -ov \
  -format UDZO \
  "${dmg_path}"
```

### Use create-dmg Tool (Advanced)

For more DMG customization options:

```bash
brew install create-dmg

create-dmg \
  --volname "Studio Pipeline" \
  --volicon "packaging/AppIcon.icns" \
  --background "packaging/dmg-background.png" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --icon "StudioPipeline.app" 150 200 \
  --app-drop-link 450 200 \
  "dist/StudioPipeline.dmg" \
  "dist/StudioPipeline.app"
```

## Bundle Size Optimization

Current estimated sizes:
- Backend (PyInstaller): ~200-300 MB
- Frontend: ~2 MB
- Swift tools: ~545 KB
- ONNX model: ~16 MB
- **Total**: ~250-350 MB

### Reduce Size

1. **Exclude unused modules** in `.spec`:
   ```python
   excludes=['pandas', 'scipy', 'matplotlib', ...]
   ```

2. **Use UPX compression** (PyInstaller):
   ```python
   exe = EXE(..., upx=True, ...)
   ```

3. **Strip debug symbols**:
   ```bash
   strip dist/StudioPipeline.app/Contents/MacOS/backend/backend
   ```

4. **Compress DMG more**:
   ```bash
   hdiutil create ... -format UDBZ  # bzip2 compression
   ```

## Environment Variables

The launcher sets these environment variables:

- `PYTHONUNBUFFERED=1` - No buffering for logs
- `PYTHONDONTWRITEBYTECODE=1` - Skip .pyc files
- `STUDIO_PIPELINE_RESOURCES` - Path to bundled resources
- `STUDIO_PIPELINE_SWIFT_TOOLS` - Path to Swift tools
- `STUDIO_PIPELINE_MODELS` - Path to ONNX model
- `STUDIO_PIPELINE_BUNDLED=1` - Flag for bundled mode

## Future Enhancements

- [ ] Add application icon (`AppIcon.icns`)
- [ ] Add DMG background image
- [ ] Add menu bar icon/tray support
- [ ] Implement auto-updates (Sparkle framework)
- [ ] Create universal binary (x86_64 + arm64)
- [ ] Submit to Mac App Store

## Resources

- [PyInstaller Documentation](https://pyinstaller.org/en/stable/)
- [macOS Code Signing Guide](https://developer.apple.com/documentation/security/code_signing_services)
- [Notarization Guide](https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution)
- [create-dmg Tool](https://github.com/create-dmg/create-dmg)

## License

Proprietary - Studio Pipeline Team
