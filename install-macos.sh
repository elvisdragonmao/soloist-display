#!/usr/bin/env bash
# Install on macOS (Apple Silicon, macOS 13+): Soloist, the display server, the
# daily updater and the display itself as LaunchAgents of the current user.
# No sudo. Needs python3 and Chrome, Chromium, Edge or Brave.
#
#   ./install-macos.sh                 install, and open the display at login
#   ./install-macos.sh --no-autostart  don't open the display at login
#   ./install-macos.sh --uninstall
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Library/Application Support/soloist-display"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs/soloist-display"
BIN="$APP/bin/soloist"
CONFIG="$APP/soloist.env"
PREFIX=org.soloist-display

if [[ "${1:-}" == "--uninstall" ]]; then
  for name in open update server soloist; do
    launchctl bootout "gui/$UID/$PREFIX.$name" 2> /dev/null || true
    rm -f "$AGENTS/$PREFIX.$name.plist"
  done
  echo "Removed the LaunchAgents. Settings and the Soloist binary stay in $APP."
  exit 0
fi

PY=$(command -v python3) || { echo "python3 is required: xcode-select --install, or brew install python" >&2; exit 1; }
mkdir -p "$APP" "$AGENTS" "$LOGS"

if [[ ! -f "$CONFIG" ]]; then
  install -m600 "$REPO/soloist/soloist.env.example" "$CONFIG"
  sed -i '' "s|^SOLOIST_DEVICE_NAME=.*|SOLOIST_DEVICE_NAME=$(scutil --get ComputerName)|" "$CONFIG"
  echo "!! Put the Soloist API key in \"$CONFIG\", then run this again"
  exit 1
fi

"$PY" "$REPO/soloist/update.py" --bin "$BIN" --restart pid --force

xml() { sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' <<< "$1"; }

# agent NAME EXTRA_PLIST_XML ARG...
agent() {
  local name=$1 extra=$2 label="$PREFIX.$1"
  shift 2
  local plist="$AGENTS/$label.plist"
  {
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    echo '<plist version="1.0"><dict>'
    echo "  <key>Label</key><string>$label</string>"
    echo '  <key>ProgramArguments</key><array>'
    for arg in "$@"; do echo "    <string>$(xml "$arg")</string>"; done
    echo '  </array>'
    echo "  <key>StandardOutPath</key><string>$(xml "$LOGS/$name.log")</string>"
    echo "  <key>StandardErrorPath</key><string>$(xml "$LOGS/$name.log")</string>"
    echo "  $extra"
    echo '</dict></plist>'
  } > "$plist"
  launchctl bootout "gui/$UID/$label" 2> /dev/null || true
  launchctl bootstrap "gui/$UID" "$plist"
}

ALWAYS='<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>'
agent soloist "$ALWAYS" "$PY" "$REPO/soloist/run.py" --bin "$BIN" --config "$CONFIG"
agent server "$ALWAYS" "$PY" "$REPO/display/server.py" --port 8787
agent update '<key>RunAtLoad</key><true/><key>StartCalendarInterval</key><dict><key>Hour</key><integer>5</integer><key>Minute</key><integer>30</integer></dict>' \
  "$PY" "$REPO/soloist/update.py" --bin "$BIN" --restart pid
if [[ "${1:-}" != "--no-autostart" ]]; then
  agent open '<key>RunAtLoad</key><true/>' "$PY" "$REPO/display/open.py"
fi

echo "Installed. Logs: $LOGS"
echo "Open the display any time: python3 \"$REPO/display/open.py\""
echo "Clicking to leave full screen needs Accessibility permission for python3"
echo "(System Settings → Privacy & Security → Accessibility); without it press ⌃⌘F."
