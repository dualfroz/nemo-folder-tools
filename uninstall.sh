#!/usr/bin/env bash
# Removes this plugin from Nemo. The core, the other plugins and the config
# file are left alone.
set -euo pipefail

dataHome="${XDG_DATA_HOME:-$HOME/.local/share}"
extensionsDir="$dataHome/nemo-python/extensions"
target="$extensionsDir/nemoFolderTools.py"

if [ -e "$target" ]; then
  rm -f "$target"
  echo "Removed $target"
else
  echo "Not installed: $target"
fi

rm -f "$extensionsDir/__pycache__/nemoFolderTools".*.pyc

echo
echo "Restart Nemo to unload it:  nemo -q"
