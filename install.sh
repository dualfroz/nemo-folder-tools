#!/usr/bin/env bash
# Installs the nemo-repo-emblems extension for the current user:
#   - symlinks the extension .py into ~/.local/share/nemo-python/extensions/
#   - symlinks the bundled emblem SVGs into ~/.local/share/icons/hicolor/scalable/emblems/
#   - creates ~/.config/nemo-repo-emblems.json from the bundled default if missing
#   - refreshes the icon cache and restarts nemo
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

EXT_DIR="$HOME/.local/share/nemo-python/extensions"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/emblems"
CONFIG_PATH="$HOME/.config/nemo-repo-emblems.json"

mkdir -p "$EXT_DIR" "$ICON_DIR" "$(dirname "$CONFIG_PATH")"

ln -sf "$SRC_DIR/nemo_repo_emblems.py" "$EXT_DIR/nemo_repo_emblems.py"
echo "Linked extension -> $EXT_DIR/nemo_repo_emblems.py"

for svg in "$SRC_DIR"/emblems/*.svg; do
  ln -sf "$svg" "$ICON_DIR/$(basename "$svg")"
done
echo "Linked emblem icons -> $ICON_DIR"

if [ ! -f "$CONFIG_PATH" ]; then
  cp "$SRC_DIR/config.default.json" "$CONFIG_PATH"
  echo "Created default config -> $CONFIG_PATH"
else
  echo "Config already exists, left untouched -> $CONFIG_PATH"
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo "Restarting nemo..."
nemo -q || true
(nemo --no-desktop >/dev/null 2>&1 &) || true

echo "Done. Edit $CONFIG_PATH to toggle indicators/actions (live-reloaded, no restart needed)."
