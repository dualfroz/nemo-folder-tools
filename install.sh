#!/usr/bin/env bash
# Installs the nemo-folder-tools plugin for the current user. No root needed.
#
#   ./install.sh          link the plugin (edits in this checkout go live)
#   ./install.sh --copy   copy the plugin instead of linking it
#
# Requires nemo-repo-core: https://github.com/dualfroz/nemo-repo-core
set -euo pipefail

sourceDir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dataHome="${XDG_DATA_HOME:-$HOME/.local/share}"
extensionsDir="$dataHome/nemo-python/extensions"
coreDir="$dataHome/nemo-repo-core"
pluginFile="nemoFolderTools.py"

mode="link"
if [ "${1:-}" = "--copy" ]; then
  mode="copy"
elif [ -n "${1:-}" ]; then
  echo "usage: $0 [--copy]" >&2
  exit 2
fi

if [ ! -d "$coreDir/nemoRepoCore" ] && ! python3 -c "import nemoRepoCore" >/dev/null 2>&1; then
  cat >&2 <<'MESSAGE'
nemo-repo-core is not installed, and this plugin is nothing without it:

  git clone https://github.com/dualfroz/nemo-repo-core
  cd nemo-repo-core && ./install.sh
MESSAGE
  exit 1
fi

mkdir -p "$extensionsDir"
target="$extensionsDir/$pluginFile"
rm -f "$target"
if [ "$mode" = "copy" ]; then
  cp "$sourceDir/$pluginFile" "$target"
  echo "Copied plugin -> $target"
else
  ln -s "$sourceDir/$pluginFile" "$target"
  echo "Linked plugin -> $target"
fi

if ! PYTHONPATH="$coreDir:$extensionsDir" python3 -c "import nemoFolderTools" >/dev/null 2>&1; then
  echo >&2
  echo "The plugin did not import cleanly:" >&2
  PYTHONPATH="$coreDir:$extensionsDir" python3 -c "import nemoFolderTools" >&2 || true
  exit 1
fi
echo "Import check passed."

legacyExtension="$extensionsDir/nemo_repo_emblems.py"
if [ -e "$legacyExtension" ]; then
  echo
  echo "WARNING: the pre-split single file extension is still installed:"
  echo "  $legacyExtension"
  echo "Running both duplicates emblems, columns and menu entries. Remove it with:"
  echo "  rm \"$legacyExtension\""
fi

echo
echo "Restart Nemo to load the plugin:  nemo -q"
