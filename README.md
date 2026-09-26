# nemo-folder-tools

nemo-folder-tools is an extension for [Nemo](https://github.com/linuxmint/nemo),
the Cinnamon file manager, that adds "Open Terminal Here" and "Open in Editor"
to the right click menu of any local folder. Nothing in it is git specific; it
uses the shared config and the terminal and editor launchers of
**nemo-repo-core**, and needs it installed.

## Features

- Two entries, on a single selected folder and on the empty background of an
  open folder:

  | Entry | What it does |
  | --- | --- |
  | Open Terminal Here | Starts the terminal emulator with the folder as its working directory |
  | Open in Editor | Runs the configured editor command with the folder as its last argument |

- An entry is only added when it can work: no terminal found means no Open
  Terminal Here, an editor command that is not in `PATH` means no Open in
  Editor.
- The terminal is the core's `terminal_command`, or the first emulator found
  of `gnome-terminal`, `x-terminal-emulator`, `tilix`, `konsole`,
  `xfce4-terminal`, `mate-terminal`, `kitty`, `alacritty`, `xterm`.
- Each entry can be switched off in the config; config changes apply on the
  next right click.

## Requirements

- nemo-repo-core 0.1.x
- Nemo with `nemo-python`
- A terminal emulator and an editor command for the respective entries

## Install and run

Install nemo-repo-core first (run `./install.sh` in its checkout), then from a
checkout of this repository:

```bash
./install.sh
nemo -q
```

`install.sh` links `nemoFolderTools.py` into
`~/.local/share/nemo-python/extensions` and checks that it imports. Pass
`--copy` to copy instead of link. It stops with a message if nemo-repo-core is
not installed. No root is required.
`./uninstall.sh` removes the plugin.

## Configuration

Settings live in the shared file `~/.config/nemo-repo-core.json`.
`config.example.json` shows the keys this plugin uses:

```json
{
  "editor_command": "code",
  "terminal_command": null,
  "actions": {
    "open_terminal": true,
    "open_editor": true
  }
}
```

| Key | Default | Meaning |
| --- | --- | --- |
| `actions.open_terminal` | `true` | Show Open Terminal Here |
| `actions.open_editor` | `true` | Show Open in Editor |
| `editor_command` | `"code"` | Core setting: editor command, may include arguments, for example `"code -n"` or `"xdg-open"` |
| `terminal_command` | `null` | Core setting: terminal to use; `null` auto detects |

`editor_command` and `terminal_command` belong to the core and are shared with
the other plugins.

## Tests

The tests use the standard library `unittest` and need PyGObject with the Nemo
typelib (`gir1.2-nemo-3.0`) and nemo-repo-core: an installed core, a checkout
of nemo-repo-core next to this one (`../nemo-repo-core`), or a path in
`NEMO_REPO_CORE_PATH`. Without the core the suite is skipped. Run them from the
repository root:

```bash
python3 -m unittest discover -s tests
```

They cover when each entry is offered (terminal found, editor installed,
config switches), the tips, what each entry launches, and which selections get
entries. The launchers are replaced during the tests, so no terminal or editor
is started, and git is not needed. The shared config is redirected to a
temporary file, so your real config is never touched.

## Project layout

```
nemoFolderTools.py        the Nemo extension
config.example.json       keys used by this plugin
install.sh, uninstall.sh  per-user install
tests/
  support.py              temporary config, git helpers and core lookup
  testFolderTools.py      unittest suite
```

## Limitations

- Only local folders are handled; remote locations get no entries.
- `editor_command` and `terminal_command` are split on single spaces; quoted
  arguments are not supported.
- Terminal-based editors such as `vim` need a wrapper command that opens a
  terminal, since the editor is started without one.

## License

MIT. See `LICENSE`.
