#!/usr/bin/env bash
# install.sh — set up lcsr and install it as a native macOS app.
#
# Requirements:
#   - macOS 12 or later
#   - Python 3.10 or later accessible as `python3`
#
# What this script does:
#   1. Verifies Python 3.10+
#   2. Creates a virtual environment (.venv) inside this repo
#   3. Installs lcsr and its desktop dependencies into the venv
#   4. Generates a macOS .app bundle pointing back at this repo
#   5. Copies the bundle to /Applications (requires your password once)
#   6. Tells Spotlight to index it immediately
#
# IMPORTANT: Do not move this folder after running install.
# The .app bundle contains the absolute path to this directory.
# If you move it, re-run this script from the new location.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="lcsr"
APP_BUNDLE="/Applications/${APP_NAME}.app"
ICON_SRC="${REPO_DIR}/src/lcsr/static/icon.png"
VENV="${REPO_DIR}/.venv"
PYTHON="${VENV}/bin/python"

# ── colours ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}✓${RESET} $*"; }
info() { echo -e "${BOLD}→${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET} $*"; }
die()  { echo -e "${RED}✗ $*${RESET}" >&2; exit 1; }

echo ""
echo -e "${BOLD}lcsr install${RESET}"
echo "──────────────────────────────────────────"
echo ""

# ── 1. check python ─────────────────────────────────────────────────────────
info "Checking Python version..."
# Prefer pyenv's shim if available, fall back to system python3.
# Explicitly exclude the repo's own .venv so we use the real interpreter.
if command -v pyenv &>/dev/null; then
  PY_BIN="$(pyenv which python3 2>/dev/null || true)"
fi
if [ -z "${PY_BIN:-}" ] || [[ "$PY_BIN" == "${VENV}"* ]]; then
  PY_BIN="$(PATH="$(echo "$PATH" | tr ':' '\n' | grep -v "${VENV}" | tr '\n' ':')" \
            command -v python3 2>/dev/null || true)"
fi
[ -z "${PY_BIN:-}" ] && die "python3 not found. Install Python 3.10+ from https://python.org and try again."

PY_VERSION="$("$PY_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION#*.}"

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  die "Python 3.10 or later is required (found ${PY_VERSION}). Download from https://python.org"
fi
ok "Python ${PY_VERSION} found at ${PY_BIN}"

# ── 2. create venv ──────────────────────────────────────────────────────────
if [ -d "$VENV" ]; then
  info "Virtual environment already exists, skipping creation."
else
  info "Creating virtual environment..."
  "$PY_BIN" -m venv "$VENV"
  ok "Virtual environment created at .venv"
fi

# ── 3. install lcsr[app] ────────────────────────────────────────────────────
info "Installing lcsr and desktop dependencies..."
"$PYTHON" -m pip install --upgrade pip --quiet
"$PYTHON" -m pip install -e "${REPO_DIR}[app]" --quiet
ok "lcsr installed"

# ── 4. generate icon.icns ───────────────────────────────────────────────────
info "Generating icon..."
ICONSET_DIR="$(mktemp -d)/lcsr.iconset"
mkdir -p "$ICONSET_DIR"

# macOS requires multiple resolutions in an iconset.
for size in 16 32 64 128 256 512; do
  sips -z $size $size "$ICON_SRC" --out "${ICONSET_DIR}/icon_${size}x${size}.png" > /dev/null 2>&1
  double=$((size * 2))
  sips -z $double $double "$ICON_SRC" --out "${ICONSET_DIR}/icon_${size}x${size}@2x.png" > /dev/null 2>&1
done

ICNS_PATH="$(dirname "$ICONSET_DIR")/lcsr.icns"
iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"
ok "Icon generated"

# ── 5. build .app bundle ────────────────────────────────────────────────────
info "Building ${APP_NAME}.app..."
STAGING="$(mktemp -d)/${APP_NAME}.app"
mkdir -p "${STAGING}/Contents/MacOS"
mkdir -p "${STAGING}/Contents/Resources"

# Info.plist — tells macOS the app name, icon, bundle ID, and that it is
# a regular GUI app (LSUIElement=false means it shows in the Dock).
cat > "${STAGING}/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>lcsr</string>
  <key>CFBundleDisplayName</key>
  <string>lcsr</string>
  <key>CFBundleIdentifier</key>
  <string>com.mjuiuc.lcsr</string>
  <key>CFBundleVersion</key>
  <string>1.0</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleExecutable</key>
  <string>lcsr</string>
  <key>CFBundleIconFile</key>
  <string>lcsr</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>LSUIElement</key>
  <false/>
</dict>
</plist>
PLIST

# Launcher script — activates the venv and runs lcsr app.
# The repo path is baked in at install time.
cat > "${STAGING}/Contents/MacOS/lcsr" << LAUNCHER
#!/usr/bin/env bash
exec "${VENV}/bin/python" -m lcsr app
LAUNCHER
chmod +x "${STAGING}/Contents/MacOS/lcsr"

# Copy the icon.
cp "$ICNS_PATH" "${STAGING}/Contents/Resources/lcsr.icns"

ok "Bundle built"

# ── 6. install to /Applications ─────────────────────────────────────────────
info "Installing to /Applications (you may be prompted for your password)..."
if [ -d "$APP_BUNDLE" ]; then
  warn "Replacing existing ${APP_BUNDLE}"
  sudo rm -rf "$APP_BUNDLE"
fi
sudo cp -r "$STAGING" "$APP_BUNDLE"
ok "Installed to ${APP_BUNDLE}"

# ── 7. tell spotlight to index it ───────────────────────────────────────────
info "Updating Spotlight index..."
mdimport "$APP_BUNDLE" 2>/dev/null || true
ok "Spotlight updated"

# ── cleanup ─────────────────────────────────────────────────────────────────
rm -rf "$(dirname "$ICONSET_DIR")" "$(dirname "$STAGING")" 2>/dev/null || true

echo ""
echo -e "${GREEN}${BOLD}All done!${RESET}"
echo ""
echo "  Open lcsr from Spotlight (⌘Space → lcsr) or from /Applications."
echo ""
echo -e "  ${YELLOW}Note:${RESET} Do not move the repo folder at:"
echo "  ${REPO_DIR}"
echo "  If you do, re-run this script from the new location."
echo ""
