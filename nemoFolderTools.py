#!/usr/bin/python3
"""nemo-folder-tools: "Open Terminal Here" and "Open in Editor" for Nemo.

Nothing here is git specific: the entries appear on any local folder. The
terminal and the editor command are configurable, and the terminal is
detected from a list of the common emulators when it is not configured.

Requires nemo-repo-core: https://github.com/dualfroz/nemo-repo-core
"""

import importlib.util
import os
import sys


def _ensureCoreOnPath():
    if importlib.util.find_spec("nemoRepoCore") is not None:
        return
    dataHome = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    dataDirs = (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    for base in [dataHome] + dataDirs:
        candidate = os.path.join(base, "nemo-repo-core")
        if os.path.isdir(os.path.join(candidate, "nemoRepoCore")):
            sys.path.insert(0, candidate)
            return


_ensureCoreOnPath()

import gi

gi.require_version("Nemo", "3.0")
from gi.repository import GObject, Nemo

from nemoRepoCore import (coreConfig, editorAvailable, launchEditor,
                          launchTerminal, localDirectoryPath, requireCore,
                          resolveTerminal)

requireCore("1.0.0")

pluginDefaults = {
    "actions": {
        "open_terminal": True,
        "open_editor": True,
    },
}

coreConfig.registerDefaults(pluginDefaults)


class FolderToolsMenuProvider(GObject.GObject, Nemo.MenuProvider,
                              Nemo.NameAndDescProvider):

    def _itemsFor(self, path):
        items = []

        if coreConfig.sectionFlag("actions", "open_terminal", True) and resolveTerminal():
            item = Nemo.MenuItem(name="NemoFolderTools::open_terminal",
                                 label="Open Terminal Here",
                                 tip="Open a terminal in %s" % path)
            item.connect("activate", lambda *arguments: launchTerminal(path))
            items.append(item)

        if coreConfig.sectionFlag("actions", "open_editor", True) and editorAvailable():
            item = Nemo.MenuItem(name="NemoFolderTools::open_editor",
                                 label="Open in Editor",
                                 tip="Open %s in %s" % (path, coreConfig.editorCommand))
            item.connect("activate", lambda *arguments: launchEditor(path))
            items.append(item)

        return items

    def get_file_items(self, window, files):
        if len(files) != 1:
            return []
        path = localDirectoryPath(files[0])
        return self._itemsFor(path) if path else []

    def get_background_items(self, window, currentFolder):
        path = localDirectoryPath(currentFolder)
        return self._itemsFor(path) if path else []

    def get_name_and_desc(self):
        return ["nemo-folder-tools:::Open Terminal Here and Open in Editor for any folder"]
