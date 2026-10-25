#!/usr/bin/env bash
# Download the latest Soloist release and install it if it differs from the
# installed binary. Spotify's Soloist builds expire 90 days after release, and
# an expired build will not recover by restarting, so this runs daily.
#
# Runs as root (soloist-update.service). The player itself is a user service of
# SOLOIST_USER, which is stopped and started around the install.
#
#   soloist-update.sh            install only if a new build exists and nothing is playing
#   soloist-update.sh --force    install even while music is playing
set -euo pipefail

URL="${SOLOIST_URL:-https://soloist-builds.spotifycdn.com/soloist_release_arm64.tar.gz}"
SOLOIST_USER="${SOLOIST_USER:-sdc}"
UNIT="${SOLOIST_UNIT:-spotify-soloist}"
BIN=/usr/local/bin/soloist
FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

user_home=$(getent passwd "$SOLOIST_USER" | cut -d: -f6)
release_dir="$user_home/apps/spotify-soloist"

user_systemctl() {
  systemctl --user --machine="$SOLOIST_USER@.host" "$@"
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

curl -fsSL --retry 3 --retry-delay 10 -o "$work/soloist.tar.gz" "$URL"
mkdir "$work/x"
tar -xzf "$work/soloist.tar.gz" -C "$work/x"
new="$work/x/soloist"

if [[ ! -f "$new" ]]; then
  echo "soloist binary not found in $URL" >&2
  exit 1
fi
chmod 755 "$new"
new_version=$("$new" --version)
old_version=$("$BIN" --version 2>/dev/null || echo "none")

if [[ -x "$BIN" ]] && cmp -s "$new" "$BIN"; then
  echo "up to date: $old_version"
  exit 0
fi

echo "installed: $old_version"
echo "available: $new_version"

active=$(user_systemctl is-active "$UNIT" || true)
if [[ $FORCE -eq 0 && "$active" == "active" ]]; then
  status=$(runuser -u "$SOLOIST_USER" -- "$BIN" ctl now --json 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))' 2>/dev/null || true)
  if [[ "$status" == "playing" ]]; then
    echo "music is playing, deferring the update (run with --force to install now)"
    exit 0
  fi
fi

user_systemctl stop "$UNIT" || true
[[ -f "$BIN" ]] && cp -p "$BIN" "$BIN.prev"
install -m 755 "$new" "$BIN"

# Keep the unpacked release (changelog, licenses) next to the old manual install.
install -d -o "$SOLOIST_USER" -g "$SOLOIST_USER" "$release_dir"
cp "$work/soloist.tar.gz" "$release_dir/soloist.tar.gz"
cp -r "$work/x/." "$release_dir/"
chown -R "$SOLOIST_USER:$SOLOIST_USER" "$release_dir"

user_systemctl start "$UNIT"
echo "updated to: $("$BIN" --version)"
