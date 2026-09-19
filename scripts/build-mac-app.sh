#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# SAM Mac App Builder
# Creates a double-clickable SAM.app in ~/Applications
# Run once: bash scripts/build-mac-app.sh
# ─────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JARVIS_DIR="$(dirname "$SCRIPT_DIR")"
APP_NAME="SAM"
APP_DIR="$HOME/Applications/${APP_NAME}.app"

echo "🤖 Building ${APP_NAME}.app..."

# Create app bundle structure
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# ── Info.plist ───────────────────────────────────────────────────
cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>SAM</string>
    <key>CFBundleIdentifier</key>
    <string>my.harnova.sam</string>
    <key>CFBundleName</key>
    <string>SAM</string>
    <key>CFBundleDisplayName</key>
    <string>SAM</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

# ── Main launcher script ─────────────────────────────────────────
cat > "$APP_DIR/Contents/MacOS/SAM" << LAUNCHER
#!/bin/bash
# SAM launcher — runs backend + frontend, opens browser
JARVIS_DIR="${JARVIS_DIR}"
LOG_DIR="\$HOME/.sam_logs"
mkdir -p "\$LOG_DIR"

# Notification helper
notify() {
    osascript -e "display notification \"\$1\" with title \"SAM\" sound name \"Ping\"" 2>/dev/null || true
}

notify "SAM is starting..."

# ── Check if already running ────────────────────────────────────
if lsof -i :8000 &>/dev/null; then
    notify "SAM is already running"
    open http://localhost:5173 2>/dev/null || open http://localhost:5174 2>/dev/null || true
    exit 0
fi

# ── Backend ─────────────────────────────────────────────────────
cd "\$JARVIS_DIR/backend"

# Find Python
PYTHON=""
for p in python3 python3.12 python3.11 python3.10 python; do
    if command -v "\$p" &>/dev/null; then
        PYTHON="\$p"
        break
    fi
done

if [ -z "\$PYTHON" ]; then
    osascript -e 'display alert "SAM Error" message "Python 3 not found. Install Python 3.10+ from python.org" as critical'
    exit 1
fi

# Install deps if needed
if ! "\$PYTHON" -c "import fastapi" 2>/dev/null; then
    notify "Installing SAM dependencies (one time)..."
    "\$PYTHON" -m pip install -r requirements.txt --quiet 2>>"\$LOG_DIR/install.log" || true
fi

# Load .env
if [ -f "\$JARVIS_DIR/.env" ]; then
    export \$(grep -v '^#' "\$JARVIS_DIR/.env" | xargs) 2>/dev/null || true
fi

# Start backend
"\$PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level warning > "\$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=\$!
echo \$BACKEND_PID > "\$LOG_DIR/backend.pid"

# ── Frontend ─────────────────────────────────────────────────────
cd "\$JARVIS_DIR/frontend"

# Find Node
NODE=""
for n in node /opt/homebrew/bin/node /usr/local/bin/node ~/.nvm/versions/node/\$(ls ~/.nvm/versions/node/ 2>/dev/null | tail -1)/bin/node; do
    if command -v "\$n" &>/dev/null || [ -f "\$n" ]; then
        NODE="\$n"
        break
    fi
done

if [ -z "\$NODE" ]; then
    notify "Node.js not found — SAM will use backend-only mode"
else
    # Install npm deps if needed
    if [ ! -d "node_modules" ]; then
        notify "Installing frontend dependencies (one time)..."
        npm install --silent 2>>"\$LOG_DIR/install.log" || true
    fi
    "\$NODE" \$(which npm 2>/dev/null || echo "npm") run dev > "\$LOG_DIR/frontend.log" 2>&1 &
    FRONTEND_PID=\$!
    echo \$FRONTEND_PID > "\$LOG_DIR/frontend.pid"
fi

# ── Wait for backend ─────────────────────────────────────────────
echo "Waiting for SAM backend..."
for i in \$(seq 1 20); do
    if curl -sf http://localhost:8000/health &>/dev/null; then
        break
    fi
    sleep 0.5
done

notify "SAM is ready!"

# ── Open browser ─────────────────────────────────────────────────
sleep 1
# Try frontend dev server first, then fall back
if curl -sf http://localhost:5173 &>/dev/null; then
    open http://localhost:5173
elif curl -sf http://localhost:5174 &>/dev/null; then
    open http://localhost:5174
else
    open http://localhost:8000
fi

# Keep alive — cleanup when terminated
wait \$BACKEND_PID 2>/dev/null
LAUNCHER

chmod +x "$APP_DIR/Contents/MacOS/SAM"

# ── Generate a simple icon ────────────────────────────────────────
# Create an SVG then convert to icns (requires sips + iconutil)
ICON_SVG="/tmp/sam_icon.svg"
cat > "$ICON_SVG" << 'SVG'
<svg width="1024" height="1024" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="bg" cx="50%" cy="35%" r="60%">
      <stop offset="0%" style="stop-color:#4f46e5"/>
      <stop offset="100%" style="stop-color:#0d0d1a"/>
    </radialGradient>
    <radialGradient id="orb" cx="40%" cy="35%" r="55%">
      <stop offset="0%" style="stop-color:#ffffff;stop-opacity:0.95"/>
      <stop offset="40%" style="stop-color:#818cf8"/>
      <stop offset="100%" style="stop-color:#312e81"/>
    </radialGradient>
  </defs>
  <rect width="1024" height="1024" rx="220" fill="url(#bg)"/>
  <circle cx="512" cy="480" r="260" fill="url(#orb)" opacity="0.95"/>
  <circle cx="440" cy="395" r="80" fill="white" opacity="0.35"/>
  <text x="512" y="840" font-family="SF Pro Display, Helvetica, Arial" font-size="140" font-weight="800" fill="white" text-anchor="middle" letter-spacing="-2" opacity="0.9">SAM</text>
</svg>
SVG

# Convert SVG to PNG at multiple sizes, then to icns
ICONSET="/tmp/SAM.iconset"
mkdir -p "$ICONSET"

for size in 16 32 64 128 256 512 1024; do
    if command -v rsvg-convert &>/dev/null; then
        rsvg-convert -w $size -h $size "$ICON_SVG" -o "$ICONSET/icon_${size}x${size}.png" 2>/dev/null || true
    elif command -v convert &>/dev/null; then
        convert -resize ${size}x${size} "$ICON_SVG" "$ICONSET/icon_${size}x${size}.png" 2>/dev/null || true
    else
        # Use sips with a background color as fallback
        sips -s format png --resampleWidth $size "$ICON_SVG" --out "$ICONSET/icon_${size}x${size}.png" 2>/dev/null || true
    fi
done

# Try to build icns
if command -v iconutil &>/dev/null && ls "$ICONSET"/*.png &>/dev/null; then
    iconutil -c icns "$ICONSET" -o "$APP_DIR/Contents/Resources/AppIcon.icns" 2>/dev/null || true
fi

# Clean up
rm -rf "$ICONSET" "$ICON_SVG"

echo ""
echo "✅ SAM.app created at: $APP_DIR"
echo ""
echo "To use:"
echo "  1. Double-click SAM in ~/Applications"
echo "  2. Or run: open '$APP_DIR'"
echo ""

# Also create a stop script
cat > "$JARVIS_DIR/scripts/stop-sam.sh" << 'STOP'
#!/bin/bash
LOG_DIR="$HOME/.sam_logs"
echo "Stopping SAM..."
[ -f "$LOG_DIR/backend.pid" ] && kill $(cat "$LOG_DIR/backend.pid") 2>/dev/null && rm "$LOG_DIR/backend.pid"
[ -f "$LOG_DIR/frontend.pid" ] && kill $(cat "$LOG_DIR/frontend.pid") 2>/dev/null && rm "$LOG_DIR/frontend.pid"
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
echo "SAM stopped."
STOP
chmod +x "$JARVIS_DIR/scripts/stop-sam.sh"

# Offer to open now
echo "Opening SAM now..."
open "$APP_DIR"
