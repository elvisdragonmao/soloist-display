#!/usr/bin/env bash
# Install on Linux (systemd): Soloist as a user service with a daily root
# updater, and the now-playing display. Run as the desktop user from the repo
# checkout; uses sudo for the root parts. macOS: install-macos.sh. Windows:
# install.ps1.
#
#   ./install.sh            soloist + display
#   ./install.sh soloist    Soloist service and auto-update timer only
#   ./install.sh display    now-playing display only
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
ENV_FILE="$CONFIG/soloist/soloist.env"
LIB=/usr/local/lib/soloist-display

install_soloist() {
  if [[ ! -f "$ENV_FILE" ]]; then
    install -Dm600 "$REPO/soloist/soloist.env.example" "$ENV_FILE"
    sed -i "s|^SOLOIST_DEVICE_NAME=.*|SOLOIST_DEVICE_NAME=$(hostname)|" "$ENV_FILE"
    echo "!! Put the Soloist API key in $ENV_FILE, then run this again"
    exit 1
  fi
  grep -q '^SOLOIST_DEVICE_NAME=' "$ENV_FILE" || echo "SOLOIST_DEVICE_NAME=$(hostname)" >> "$ENV_FILE"

  # The updater runs as root, installs to /usr/local/bin and restarts the user service.
  sudo install -Dm644 "$REPO/soloist/update.py" "$LIB/update.py"
  sudo tee /usr/local/sbin/soloist-update > /dev/null <<EOF
#!/bin/sh
exec /usr/bin/python3 $LIB/update.py --bin /usr/local/bin/soloist --restart systemd:spotify-soloist --user $USER "\$@"
EOF
  sudo chmod 755 /usr/local/sbin/soloist-update
  sudo install -m644 "$REPO/soloist/soloist-update.service" "$REPO/soloist/soloist-update.timer" /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now soloist-update.timer
  [[ -x /usr/local/bin/soloist ]] || sudo /usr/local/sbin/soloist-update

  install -Dm644 "$REPO/soloist/spotify-soloist.service" "$CONFIG/systemd/user/spotify-soloist.service"
  systemctl --user daemon-reload
  systemctl --user enable spotify-soloist.service
  systemctl --user is-active -q spotify-soloist.service || systemctl --user start spotify-soloist.service
}

install_display() {
  # A Chromium-family browser, Inter for the UI, and on wlroots compositors
  # (labwc, sway…) wlrctl and wtype to switch the window and toggle full screen.
  if command -v apt-get > /dev/null; then
    sudo apt-get install -y -q chromium fonts-inter wlrctl wtype > /dev/null
  else
    echo "Install a Chromium-family browser and the Inter font; on Wayland also wlrctl and wtype, on X11 xdotool."
  fi

  sed "s|%h/apps/soloist-display|$REPO|" "$REPO/display/soloist-display.service" \
    > "$CONFIG/systemd/user/soloist-display.service"
  systemctl --user daemon-reload
  systemctl --user enable soloist-display.service
  systemctl --user restart soloist-display.service

  install -d "$HOME/.local/bin"
  cat > "$HOME/.local/bin/soloist-display-open" <<EOF
#!/bin/sh
exec python3 $REPO/display/open.py "\$@"
EOF
  chmod 755 "$HOME/.local/bin/soloist-display-open"
  local desktop
  desktop=$(sed "s|@HOME@|$HOME|" "$REPO/display/soloist-display.desktop")
  install -d "$HOME/.local/share/applications" "$CONFIG/autostart"
  echo "$desktop" > "$HOME/.local/share/applications/soloist-display.desktop"
  echo "$desktop" > "$CONFIG/autostart/soloist-display.desktop"

  # On labwc, Ctrl+Alt+P brings the display back. labwc runs with
  # --merge-config, so the user rc.xml only needs the extra keybind.
  local rc="$CONFIG/labwc/rc.xml"
  if [[ -d "$CONFIG/labwc" ]] && ! grep -qs soloist-display-open "$rc"; then
    local keybind="<keyboard><keybind key=\"C-A-p\"><action name=\"Execute\" command=\"$HOME/.local/bin/soloist-display-open\" /></keybind></keyboard>"
    [[ -f "$rc" ]] || echo '<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc"/>' > "$rc"
    cp "$rc" "$rc.bak"
    python3 - "$rc" "$keybind" <<'EOF'
import re, sys
path, keybind = sys.argv[1], sys.argv[2]
xml = open(path).read()
if re.search(r"<openbox_config[^>]*/>", xml):
    xml = re.sub(r"<openbox_config([^>]*)/>", lambda m: f"<openbox_config{m[1]}>\n  {keybind}\n</openbox_config>", xml)
else:
    xml = xml.replace("</openbox_config>", f"  {keybind}\n</openbox_config>")
open(path, "w").write(xml)
EOF
    pkill -HUP -x labwc || true
  fi
}

case "${1:-all}" in
  soloist) install_soloist ;;
  display) install_display ;;
  all) install_soloist; install_display ;;
  *) echo "usage: $0 [all|soloist|display]" >&2; exit 2 ;;
esac
