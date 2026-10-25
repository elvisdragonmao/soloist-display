#!/usr/bin/env bash
# Copy this repo to the Pi and run install.sh there.
#
#   ./deploy.sh [all|soloist|display]
#   PI=other-host ./deploy.sh
set -euo pipefail

PI="${PI:-har}"
DEST="${DEST:-apps/soloist-display}"

cd "$(dirname "$0")"
rsync -a --delete --exclude .git ./ "$PI:$DEST/"
ssh -t "$PI" "cd $DEST && ./install.sh ${1:-all}"
