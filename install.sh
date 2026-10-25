#!/usr/bin/env bash
# Install everything on the Raspberry Pi. Run as the desktop user (sdc) from
# the repo checkout on the Pi; uses sudo for the root parts.
#
#   ./install.sh            soloist + display
#   ./install.sh soloist    Soloist service and auto-update timer only
#   ./install.sh display    now-playing display only
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"

install_soloist() {
  install -Dm644 "$REPO/soloist/spotify-soloist.service" "$CONFIG/systemd/user/spotify-soloist.service"
  if [[ ! -f "$CONFIG/soloist/soloist.env" ]]; then
    install -Dm600 "$REPO/soloist/soloist.env.example" "$CONFIG/soloist/soloist.env"
    echo "!! Put the Soloist API key in $CONFIG/soloist/soloist.env"
  fi
  systemctl --user daemon-reload
  systemctl --user enable spotify-soloist.service

  sudo install -m755 "$REPO/soloist/soloist-update.sh" /usr/local/sbin/soloist-update
  sudo install -m644 "$REPO/soloist/soloist-update.service" "$REPO/soloist/soloist-update.timer" /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now soloist-update.timer
}

install_display() {
  sudo apt-get install -y -q chromium fonts-inter wlrctl >/dev/null

  sed "s|%h/apps/soloist-display|$REPO|" "$REPO/display/soloist-display.service" \
    > "$CONFIG/systemd/user/soloist-display.service"
  systemctl --user daemon-reload
  systemctl --user enable soloist-display.service
  systemctl --user restart soloist-display.service

  install -Dm755 "$REPO/display/soloist-display-open" "$HOME/.local/bin/soloist-display-open"
  local desktop
  desktop=$(sed "s|@HOME@|$HOME|" "$REPO/display/soloist-display.desktop")
  install -d "$HOME/.local/share/applications" "$CONFIG/autostart"
  echo "$desktop" > "$HOME/.local/share/applications/soloist-display.desktop"
  echo "$desktop" > "$CONFIG/autostart/soloist-display.desktop"

  # Ctrl+Alt+P brings the display back. labwc runs with --merge-config, so the
  # user rc.xml only needs the extra keybind.
  local rc="$CONFIG/labwc/rc.xml"
  local keybind="<keyboard><keybind key=\"C-A-p\"><action name=\"Execute\" command=\"$HOME/.local/bin/soloist-display-open\" /></keybind></keyboard>"
  [[ -f "$rc" ]] || echo '<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc"/>' > "$rc"
  if ! grep -q soloist-display-open "$rc"; then
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
