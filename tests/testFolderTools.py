import unittest
from unittest import mock

import support
from support import FakeNemoFile, makeDirectory, resetSharedState, writeConfig, writeFile

plugin = support.importPlugin("nemoFolderTools")

from nemoRepoCore import coreConfig

terminalName = "NemoFolderTools::open_terminal"
editorName = "NemoFolderTools::open_editor"


class FolderToolsTestCase(unittest.TestCase):

    def setUp(self):
        resetSharedState()
        self.addCleanup(resetSharedState)
        self.patches = {}
        for name, value in (("resolveTerminal", "xterm"), ("editorAvailable", True),
                            ("launchTerminal", None), ("launchEditor", None)):
            patcher = mock.patch.object(plugin, name)
            self.patches[name] = patcher.start()
            self.addCleanup(patcher.stop)
            if value is not None:
                self.patches[name].return_value = value
        self.provider = plugin.FolderToolsMenuProvider()
        self.folder = makeDirectory()

    def names(self, items):
        return [item.props.name for item in items]


class EntryTests(FolderToolsTestCase):

    def testBothEntries(self):
        items = self.provider._itemsFor(self.folder)
        self.assertEqual(self.names(items), [terminalName, editorName])
        self.assertEqual([item.props.label for item in items],
                         ["Open Terminal Here", "Open in Editor"])

    def testTips(self):
        writeConfig(coreConfig, {"editor_command": "zed --new"})
        terminalItem, editorItem = self.provider._itemsFor(self.folder)
        self.assertEqual(terminalItem.props.tip, "Open a terminal in %s" % self.folder)
        self.assertEqual(editorItem.props.tip, "Open %s in zed --new" % self.folder)

    def testDefaultEditorInTip(self):
        editorItem = self.provider._itemsFor(self.folder)[1]
        self.assertTrue(editorItem.props.tip.endswith(" in code"))

    def testTerminalActivation(self):
        terminalItem = self.provider._itemsFor(self.folder)[0]
        terminalItem.activate()
        self.patches["launchTerminal"].assert_called_once_with(self.folder)
        self.patches["launchEditor"].assert_not_called()

    def testEditorActivation(self):
        editorItem = self.provider._itemsFor(self.folder)[1]
        editorItem.activate()
        self.patches["launchEditor"].assert_called_once_with(self.folder)
        self.patches["launchTerminal"].assert_not_called()

    def testNoTerminalFound(self):
        self.patches["resolveTerminal"].return_value = None
        self.assertEqual(self.names(self.provider._itemsFor(self.folder)), [editorName])

    def testEditorNotInstalled(self):
        self.patches["editorAvailable"].return_value = False
        self.assertEqual(self.names(self.provider._itemsFor(self.folder)), [terminalName])

    def testTerminalSwitchedOff(self):
        writeConfig(coreConfig, {"actions": {"open_terminal": False}})
        self.assertEqual(self.names(self.provider._itemsFor(self.folder)), [editorName])

    def testEditorSwitchedOff(self):
        writeConfig(coreConfig, {"actions": {"open_editor": {"enabled": False}}})
        self.assertEqual(self.names(self.provider._itemsFor(self.folder)), [terminalName])

    def testDefaultsRegistered(self):
        actions = coreConfig.section("actions")
        self.assertTrue(actions["open_terminal"])
        self.assertTrue(actions["open_editor"])


class SelectionTests(FolderToolsTestCase):

    def testSingleFolder(self):
        items = self.provider.get_file_items(None, [FakeNemoFile(self.folder)])
        self.assertEqual(self.names(items), [terminalName, editorName])

    def testSeveralFolders(self):
        files = [FakeNemoFile(self.folder), FakeNemoFile(makeDirectory())]
        self.assertEqual(self.provider.get_file_items(None, files), [])

    def testRegularFile(self):
        path = writeFile(self.folder, "file.txt")
        self.assertEqual(self.provider.get_file_items(None, [FakeNemoFile(path, isDirectory=False)]), [])

    def testRemoteFolder(self):
        self.assertEqual(self.provider.get_file_items(None, [FakeNemoFile("/x", scheme="sftp")]), [])

    def testBackground(self):
        items = self.provider.get_background_items(None, FakeNemoFile(self.folder))
        self.assertEqual(self.names(items), [terminalName, editorName])

    def testRemoteBackground(self):
        self.assertEqual(self.provider.get_background_items(None, FakeNemoFile("/x", scheme="smb")), [])

    def testNameAndDescription(self):
        [entry] = self.provider.get_name_and_desc()
        self.assertTrue(entry.startswith("nemo-folder-tools:::"))


if __name__ == "__main__":
    unittest.main()
