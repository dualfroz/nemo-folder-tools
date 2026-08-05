# nemo-folder-tools

"Open Terminal Here" and "Open in Editor" in the right click menu of
[Nemo](https://github.com/linuxmint/nemo), the Cinnamon file manager.

Two entries, on any local folder, on the folder icon and on the empty
background of an open folder:

| Entry | What it does |
| --- | --- |
| Open Terminal Here | Opens your terminal emulator with the folder as its working directory |
| Open in Editor | Opens the folder in the editor you configured, `code` by default |

Nothing here is git specific. It is the part of a larger repository plugin that
turned out to be useful everywhere, so it is packaged on its own.

An entry is only added when it can actually work: no terminal on the system
means no Open Terminal Here, an editor command that is not installed means no
Open in Editor, rather than a menu entry that silently does nothing.

## Requirements

- [nemo-repo-core](https://github.com/dualfroz/nemo-repo-core) 1.x, for the
  shared config file and the launcher helpers
- Nemo with `nemo-python`
- A terminal emulator. `gnome-terminal`, `tilix`, `konsole`, `xfce4-terminal`,
  `mate-terminal`, `kitty`, `alacritty` and `xterm` are detected automatically;
  anything else can be named in the config.

## Install

```bash
git clone https://github.com/dualfroz/nemo-repo-core
cd nemo-repo-core && ./install.sh && cd ..

git clone https://github.com/dualfroz/nemo-folder-tools
cd nemo-folder-tools && ./install.sh

nemo -q
```

`install.sh` links the plugin into `~/.local/share/nemo-python/extensions` and
checks that it imports. Pass `--copy` to copy instead of link. `./uninstall.sh`
removes it. Nothing is written outside your home directory and no root is
required.

## Configuration

Shared file, read live, no restart needed:

```
~/.config/nemo-repo-core.json
```

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
| `actions.open_terminal` | `true` | Show the Open Terminal Here entry |
| `actions.open_editor` | `true` | Show the Open in Editor entry |
| `editor_command` | `"code"` | Command to open the folder with. May include arguments, for example `"code -n"` |
| `terminal_command` | `null` | Terminal to use; `null` auto detects |

`editor_command` and `terminal_command` belong to the core and are shared with
the other plugins in the family, so setting your editor once covers all of
them.

Some editors people set here: `code`, `codium`, `subl`, `zed`, `nvim` inside a
terminal wrapper, or `xdg-open` to hand the folder to whatever the desktop
considers the default.

## Migrating from the single file version

These two entries used to live in `nemo_repo_emblems.py` together with git
emblems, columns, a properties tab and git menu actions. They work on every
folder and have nothing to do with git, so they are their own plugin now. The
git actions moved to
[nemo-repo-git-menu](https://github.com/dualfroz/nemo-repo-git-menu).

One change worth knowing: the Open in Editor entry used to appear only when
Visual Studio Code specifically was installed, no matter what `editor_command`
said. It now checks the command you actually configured.

Your config carries over automatically, and the old file is not modified.
Remove the old extension so the entries are not listed twice:

```bash
rm ~/.local/share/nemo-python/extensions/nemo_repo_emblems.py
nemo -q
```

## Tested on

Linux Mint 22.2 (Zara), Cinnamon 6.4.14, Nemo 6.4.5, python-nemo 6.4.0,
Python 3.12.3, with `gnome-terminal` and `code`.

## License

MIT. See `LICENSE`.
