#!/usr/bin/env bash
# Copy the FoxAgent SQLite file and settings key. Pause is not required.
set -euo pipefail
DATA_DIR="${FOXAGENT_DATA_DIR:-/opt/foxagent/data}"
DEST="${1:-$DATA_DIR/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$DEST"
if [[ -f "$DATA_DIR/foxagent.db" ]]; then
  cp -a "$DATA_DIR/foxagent.db" "$DEST/foxagent-$STAMP.db"
fi
if [[ -f "$DATA_DIR/.foxagent.key" ]]; then
  cp -a "$DATA_DIR/.foxagent.key" "$DEST/foxagent-$STAMP.key"
fi
echo "backup written under $DEST"
