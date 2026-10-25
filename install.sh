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

case "${1:-all}" in
  soloist) install_soloist ;;
  all) install_soloist ;;
  *) echo "usage: $0 [all|soloist]" >&2; exit 2 ;;
esac
