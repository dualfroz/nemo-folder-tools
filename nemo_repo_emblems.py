#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
nemo-repo-emblems
==================

A single nemo-python extension that gives Nemo (Cinnamon's file manager)
real awareness of git repositories:

  * Nemo.InfoProvider   -> configurable emblem overlays (git repo / .claude
                            dir / uncommitted changes / unpushed commits)
  * Nemo.ColumnProvider -> "Git Branch" / "Git Status" columns for list view
  * Nemo.PropertyPageProvider -> a "Git" tab in the folder's Properties
                            dialog with branch, ahead/behind, dirty counts,
                            untracked count and last commit
  * Nemo.MenuProvider   -> right-click actions: open terminal here, open in
                            editor, git status / git log / git pull in a
                            terminal

Config file: ~/.config/nemo-repo-emblems.json (created from
config.default.json next to this file on first run if missing). Edits are
picked up live via a file monitor -- no Nemo restart needed.

Performance: every git-derived fact for a repo root is cached with a TTL
(default 5s, see "cache_ttl_seconds") AND eagerly invalidated by watching
.git/HEAD, .git/index and .git/refs/heads for changes, so emblems update
promptly after a commit/checkout/pull without shelling out to git on every
Nemo redraw.
"""

import json
import logging
import os
import shutil
import subprocess
import time
import weakref

import gi
gi.require_version("Nemo", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gio, GLib, Gtk, Nemo

logger = logging.getLogger("nemo-repo-emblems")
logging.basicConfig(level=logging.WARNING)

CONFIG_PATH = os.path.expanduser("~/.config/nemo-repo-emblems.json")
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.default.json")

GIT_BIN = shutil.which("git")
CODE_BIN = shutil.which("code")
TERMINAL_CANDIDATES = ["gnome-terminal", "x-terminal-emulator", "tilix", "konsole",
                        "xfce4-terminal", "mate-terminal", "xterm"]


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "cache_ttl_seconds": 5,
    "indicators": {
        "git_repo": {"enabled": True, "emblem": "emblem-repo-git"},
        "claude_dir": {"enabled": True, "emblem": "emblem-repo-claude"},
        "uncommitted_changes": {"enabled": True, "emblem": "emblem-repo-dirty"},
        "unpushed_commits": {"enabled": True, "emblem": "emblem-repo-unpushed"},
    },
    "actions": {
        "open_terminal": True,
        "open_editor": True,
        "git_status": True,
        "git_log": True,
        "git_pull": True,
    },
    "editor_command": "code",
    "terminal_command": None,
}


class Config:
    """Loads ~/.config/nemo-repo-emblems.json and reloads it live on change."""

    def __init__(self):
        self.data = dict(DEFAULT_CONFIG)
        self._ensure_file_exists()
        self._load()
        self._monitor = None
        self._watch()

    def _ensure_file_exists(self):
        if os.path.exists(CONFIG_PATH):
            return
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        try:
            if os.path.exists(DEFAULT_CONFIG_PATH):
                shutil.copyfile(DEFAULT_CONFIG_PATH, CONFIG_PATH)
            else:
                with open(CONFIG_PATH, "w") as f:
                    json.dump(DEFAULT_CONFIG, f, indent=2)
        except OSError as e:
            logger.warning("Could not create default config at %s: %s", CONFIG_PATH, e)

    def _load(self):
        try:
            with open(CONFIG_PATH) as f:
                loaded = json.load(f)
            merged = dict(DEFAULT_CONFIG)
            merged["indicators"] = {**DEFAULT_CONFIG["indicators"], **loaded.get("indicators", {})}
            merged["actions"] = {**DEFAULT_CONFIG["actions"], **loaded.get("actions", {})}
            merged["cache_ttl_seconds"] = loaded.get("cache_ttl_seconds", DEFAULT_CONFIG["cache_ttl_seconds"])
            merged["editor_command"] = loaded.get("editor_command", DEFAULT_CONFIG["editor_command"])
            merged["terminal_command"] = loaded.get("terminal_command", DEFAULT_CONFIG["terminal_command"])
            self.data = merged
            logger.info("Loaded config from %s", CONFIG_PATH)
        except (OSError, ValueError) as e:
            logger.warning("Failed to load %s (%s), using defaults", CONFIG_PATH, e)
            self.data = dict(DEFAULT_CONFIG)

    def _watch(self):
        try:
            gfile = Gio.File.new_for_path(CONFIG_PATH)
            self._monitor = gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self._monitor.connect("changed", self._on_changed)
        except GLib.Error as e:
            logger.warning("Could not watch config file: %s", e)

    def _on_changed(self, monitor, file, other_file, event_type):
        if event_type in (Gio.FileMonitorEvent.CHANGES_DONE_HINT, Gio.FileMonitorEvent.CREATED):
            self._load()

    def indicator(self, name):
        return self.data["indicators"].get(name, {"enabled": False, "emblem": ""})

    def indicator_enabled(self, name):
        return bool(self.indicator(name).get("enabled"))

    def indicator_emblem(self, name):
        return self.indicator(name).get("emblem", "")

    def action_enabled(self, name):
        return bool(self.data["actions"].get(name, False))

    @property
    def ttl(self):
        try:
            return float(self.data.get("cache_ttl_seconds", 5))
        except (TypeError, ValueError):
            return 5.0

    @property
    def editor_command(self):
        return self.data.get("editor_command") or "code"

    @property
    def terminal_command(self):
        return self.data.get("terminal_command")


CONFIG = Config()


# --------------------------------------------------------------------------
# Git status gathering + cache
# --------------------------------------------------------------------------

class RepoInfo:
    __slots__ = ("branch", "upstream", "ahead", "behind", "has_upstream",
                 "staged", "unstaged", "untracked", "last_commit", "error")

    def __init__(self):
        self.branch = None
        self.upstream = None
        self.ahead = 0
        self.behind = 0
        self.has_upstream = False
        self.staged = 0
        self.unstaged = 0
        self.untracked = 0
        self.last_commit = None  # (hash, author, relative_date, subject)
        self.error = None

    @property
    def dirty(self):
        return (self.staged + self.unstaged + self.untracked) > 0

    @property
    def unpushed(self):
        # No upstream at all is also surfaced as "unpushed" (nothing to push TO)
        return self.ahead > 0 or not self.has_upstream


def _run_git(args, cwd):
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(
            [GIT_BIN] + args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            timeout=3,
        )
        return result.stdout.decode("utf-8", "replace")
    except (subprocess.TimeoutExpired, OSError):
        return None


def compute_repo_info(repo_root):
    info = RepoInfo()
    if not GIT_BIN:
        info.error = "git not found in PATH"
        return info

    out = _run_git(["status", "--porcelain=2", "--branch"], repo_root)
    if out is None:
        info.error = "git status failed"
        return info

    for line in out.splitlines():
        if line.startswith("# branch.head "):
            info.branch = line.split(" ", 2)[2]
        elif line.startswith("# branch.upstream "):
            info.upstream = line.split(" ", 2)[2]
            info.has_upstream = True
        elif line.startswith("# branch.ab "):
            parts = line.split(" ")
            for p in parts[2:]:
                if p.startswith("+"):
                    info.ahead = int(p[1:])
                elif p.startswith("-"):
                    info.behind = int(p[1:])
        elif line.startswith("1 ") or line.startswith("2 "):
            # ordinary / renamed-copied change: XY <sub> ...
            xy = line.split(" ", 2)[1]
            x, y = xy[0], xy[1]
            if x != ".":
                info.staged += 1
            if y != ".":
                info.unstaged += 1
        elif line.startswith("u "):
            info.staged += 1  # unmerged conflict, counts as needing attention
        elif line.startswith("? "):
            info.untracked += 1

    log_out = _run_git(["log", "-1", "--format=%h%x09%an%x09%ar%x09%s"], repo_root)
    if log_out:
        parts = log_out.strip("\n").split("\t")
        if len(parts) == 4:
            info.last_commit = tuple(parts)

    return info


class RepoCache:
    """TTL cache + git-directory file-watch invalidation, keyed by repo root path."""

    def __init__(self, ttl_fn):
        self._ttl_fn = ttl_fn
        self._entries = {}   # repo_root -> (RepoInfo, timestamp)
        self._monitors = {}  # repo_root -> [Gio.FileMonitor, ...]
        self._watchers = {}  # repo_root -> weakref.WeakSet[Nemo.FileInfo]

    def get(self, repo_root):
        now = time.monotonic()
        entry = self._entries.get(repo_root)
        if entry is not None:
            info, ts = entry
            if (now - ts) < self._ttl_fn():
                return info
        info = compute_repo_info(repo_root)
        self._entries[repo_root] = (info, now)
        self._ensure_watch(repo_root)
        return info

    def register_file_object(self, repo_root, nemo_file):
        """Track a live Nemo.FileInfo so we can force a re-query on git changes."""
        watchers = self._watchers.setdefault(repo_root, weakref.WeakSet())
        try:
            watchers.add(nemo_file)
        except TypeError:
            pass

    def _ensure_watch(self, repo_root):
        if repo_root in self._monitors:
            return
        git_dir = os.path.join(repo_root, ".git")
        # .git can be a file (worktrees / submodules) instead of a directory
        if os.path.isfile(git_dir):
            return
        if not os.path.isdir(git_dir):
            return

        monitors = []
        watch_paths = [
            git_dir,                              # HEAD, index, MERGE_HEAD, ...
            os.path.join(git_dir, "refs", "heads"),  # local branch tip updates
        ]
        for path in watch_paths:
            if not os.path.exists(path):
                continue
            try:
                gfile = Gio.File.new_for_path(path)
                monitor = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
                monitor.connect("changed", self._on_git_dir_changed, repo_root)
                monitors.append(monitor)
            except GLib.Error as e:
                logger.debug("Could not watch %s: %s", path, e)
        if monitors:
            self._monitors[repo_root] = monitors

    def _on_git_dir_changed(self, monitor, gfile, other_file, event_type, repo_root):
        # Invalidate immediately rather than waiting for TTL expiry.
        self._entries.pop(repo_root, None)
        for nemo_file in list(self._watchers.get(repo_root, ())):
            try:
                nemo_file.invalidate_extension_info()
            except Exception:
                pass


CACHE = RepoCache(lambda: CONFIG.ttl)


def find_repo_root(path):
    """A directory is a repo root, for our purposes, if it directly contains .git."""
    if os.path.isdir(os.path.join(path, ".git")) or os.path.isfile(os.path.join(path, ".git")):
        return path
    return None


def has_claude_dir(path):
    return os.path.isdir(os.path.join(path, ".claude"))


# --------------------------------------------------------------------------
# InfoProvider: emblems
# --------------------------------------------------------------------------

class RepoEmblemProvider(GObject.GObject, Nemo.InfoProvider, Nemo.NameAndDescProvider):

    def update_file_info(self, file):
        if file.get_uri_scheme() != "file":
            return
        if not file.is_directory():
            return

        path = GLib.filename_from_uri(file.get_uri())[0]

        if CONFIG.indicator_enabled("claude_dir") and has_claude_dir(path):
            emblem = CONFIG.indicator_emblem("claude_dir")
            if emblem:
                file.add_emblem(emblem)

        repo_root = find_repo_root(path)
        if repo_root is None:
            return

        if CONFIG.indicator_enabled("git_repo"):
            emblem = CONFIG.indicator_emblem("git_repo")
            if emblem:
                file.add_emblem(emblem)

        # Only shell out / consult the cache if we actually need dirty/unpushed state.
        if CONFIG.indicator_enabled("uncommitted_changes") or CONFIG.indicator_enabled("unpushed_commits"):
            CACHE.register_file_object(repo_root, file)
            info = CACHE.get(repo_root)

            if info.error is None:
                if CONFIG.indicator_enabled("uncommitted_changes") and info.dirty:
                    emblem = CONFIG.indicator_emblem("uncommitted_changes")
                    if emblem:
                        file.add_emblem(emblem)
                if CONFIG.indicator_enabled("unpushed_commits") and info.unpushed:
                    emblem = CONFIG.indicator_emblem("unpushed_commits")
                    if emblem:
                        file.add_emblem(emblem)

    def get_name_and_desc(self):
        return [("nemo-repo-emblems:::Configurable git-status emblems (.git / .claude / dirty / unpushed)")]


# --------------------------------------------------------------------------
# ColumnProvider: extra list-view columns
# --------------------------------------------------------------------------

class RepoColumnProvider(GObject.GObject, Nemo.ColumnProvider, Nemo.InfoProvider, Nemo.NameAndDescProvider):

    def get_columns(self):
        return [
            Nemo.Column(name="NemoRepoEmblems::branch_column",
                        attribute="repo_branch",
                        label="Git Branch",
                        description="Current branch of the git repository"),
            Nemo.Column(name="NemoRepoEmblems::status_column",
                        attribute="repo_status",
                        label="Git Status",
                        description="Ahead/behind + working tree status"),
        ]

    def update_file_info(self, file):
        if file.get_uri_scheme() != "file" or not file.is_directory():
            return

        path = GLib.filename_from_uri(file.get_uri())[0]
        repo_root = find_repo_root(path)
        if repo_root is None:
            file.add_string_attribute("repo_branch", "")
            file.add_string_attribute("repo_status", "")
            return

        CACHE.register_file_object(repo_root, file)
        info = CACHE.get(repo_root)

        if info.error:
            file.add_string_attribute("repo_branch", "?")
            file.add_string_attribute("repo_status", info.error)
            return

        file.add_string_attribute("repo_branch", info.branch or "(detached)")

        bits = []
        if info.ahead:
            bits.append(f"↑{info.ahead}")
        if info.behind:
            bits.append(f"↓{info.behind}")
        if not info.has_upstream:
            bits.append("no upstream")
        dirty_bits = []
        if info.staged or info.unstaged:
            dirty_bits.append(f"{info.staged + info.unstaged} changed")
        if info.untracked:
            dirty_bits.append(f"{info.untracked} untracked")
        if dirty_bits:
            bits.append("+".join(dirty_bits))
        file.add_string_attribute("repo_status", ", ".join(bits) if bits else "clean")

    def get_name_and_desc(self):
        return [("nemo-repo-emblems-columns:::Git Branch / Git Status list-view columns")]


# --------------------------------------------------------------------------
# PropertyPageProvider: "Git" tab in Properties dialog
# --------------------------------------------------------------------------

class RepoPropertyPageProvider(GObject.GObject, Nemo.PropertyPageProvider, Nemo.NameAndDescProvider):

    def get_property_pages(self, files):
        if len(files) != 1:
            return []
        file = files[0]
        if file.get_uri_scheme() != "file" or not file.is_directory():
            return []

        path = GLib.filename_from_uri(file.get_uri())[0]
        repo_root = find_repo_root(path)
        if repo_root is None:
            return []

        info = CACHE.get(repo_root)

        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(12)
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_top(12)
        grid.set_margin_bottom(12)

        def add_row(row, label_text, value_text):
            lbl = Gtk.Label(label=label_text)
            lbl.set_xalign(0)
            lbl.get_style_context().add_class("dim-label")
            val = Gtk.Label(label=value_text)
            val.set_xalign(0)
            val.set_selectable(True)
            val.set_line_wrap(True)
            grid.attach(lbl, 0, row, 1, 1)
            grid.attach(val, 1, row, 1, 1)

        if info.error:
            add_row(0, "Status", info.error)
        else:
            row = 0
            add_row(row, "Repository", repo_root); row += 1
            add_row(row, "Branch", info.branch or "(detached HEAD)"); row += 1
            add_row(row, "Upstream", info.upstream if info.has_upstream else "(none)"); row += 1
            add_row(row, "Ahead / Behind", f"{info.ahead} ahead, {info.behind} behind"); row += 1
            add_row(row, "Staged changes", str(info.staged)); row += 1
            add_row(row, "Unstaged changes", str(info.unstaged)); row += 1
            add_row(row, "Untracked files", str(info.untracked)); row += 1
            if info.last_commit:
                h, author, when, subject = info.last_commit
                add_row(row, "Last commit", f"{h} — {subject}"); row += 1
                add_row(row, "", f"by {author}, {when}"); row += 1

        grid.show_all()
        label = Gtk.Label(label="Git")
        return [Nemo.PropertyPage(name="NemoRepoEmblems::git_page", label=label, page=grid)]

    def get_name_and_desc(self):
        return [("nemo-repo-emblems-properties:::\"Git\" tab in the folder Properties dialog")]


# --------------------------------------------------------------------------
# MenuProvider: right-click actions
# --------------------------------------------------------------------------

def _resolve_terminal():
    configured = CONFIG.terminal_command
    if configured and shutil.which(configured.split(" ")[0]):
        return configured
    for candidate in TERMINAL_CANDIDATES:
        if shutil.which(candidate):
            return candidate
    return None


def _launch_terminal(path, shell_command=None):
    term = _resolve_terminal()
    if not term:
        logger.warning("No terminal emulator found")
        return
    try:
        if shell_command:
            inner = f"cd {GLib.shell_quote(path)} && {shell_command}; exec bash"
            subprocess.Popen([term, "--", "bash", "-c", inner], cwd=path)
        else:
            subprocess.Popen([term], cwd=path)
    except OSError as e:
        logger.warning("Failed to launch terminal (%s): %s", term, e)


def _launch_editor(path):
    editor = CONFIG.editor_command
    binary = shutil.which(editor.split(" ")[0]) if editor else None
    if not binary:
        logger.warning("Editor command %r not found in PATH", editor)
        return
    try:
        subprocess.Popen(editor.split(" ") + [path])
    except OSError as e:
        logger.warning("Failed to launch editor: %s", e)


class RepoMenuProvider(GObject.GObject, Nemo.MenuProvider, Nemo.NameAndDescProvider):

    def _build_items(self, path, repo_root):
        items = []
        is_repo = repo_root is not None

        if CONFIG.action_enabled("open_terminal"):
            item = Nemo.MenuItem(name="NemoRepoEmblems::open_terminal",
                                  label="Open Terminal Here",
                                  tip=f"Open a terminal in {path}")
            item.connect("activate", lambda *_: _launch_terminal(path))
            items.append(item)

        if CONFIG.action_enabled("open_editor") and CODE_BIN:
            item = Nemo.MenuItem(name="NemoRepoEmblems::open_editor",
                                  label="Open in Editor",
                                  tip=f"Open {path} in {CONFIG.editor_command}")
            item.connect("activate", lambda *_: _launch_editor(path))
            items.append(item)

        if is_repo and GIT_BIN:
            if CONFIG.action_enabled("git_status"):
                item = Nemo.MenuItem(name="NemoRepoEmblems::git_status",
                                      label="Git Status (terminal)",
                                      tip="Run git status in a terminal")
                item.connect("activate", lambda *_: _launch_terminal(repo_root, "git status"))
                items.append(item)

            if CONFIG.action_enabled("git_log"):
                item = Nemo.MenuItem(name="NemoRepoEmblems::git_log",
                                      label="Git Log (terminal)",
                                      tip="Run git log in a terminal")
                item.connect("activate", lambda *_: _launch_terminal(
                    repo_root, "git log --oneline --graph --decorate -30"))
                items.append(item)

            if CONFIG.action_enabled("git_pull"):
                item = Nemo.MenuItem(name="NemoRepoEmblems::git_pull",
                                      label="Git Pull (terminal)",
                                      tip="Run git pull in a terminal")
                item.connect("activate", lambda *_: _launch_terminal(repo_root, "git pull"))
                items.append(item)

        return items

    def get_file_items(self, window, files):
        if len(files) != 1 or not files[0].is_directory():
            return []
        file = files[0]
        if file.get_uri_scheme() != "file":
            return []
        path = GLib.filename_from_uri(file.get_uri())[0]
        return self._build_items(path, find_repo_root(path))

    def get_background_items(self, window, current_folder):
        if current_folder.get_uri_scheme() != "file":
            return []
        path = GLib.filename_from_uri(current_folder.get_uri())[0]
        return self._build_items(path, find_repo_root(path))

    def get_name_and_desc(self):
        return [("nemo-repo-emblems-menu:::Repo-aware right-click actions (terminal / editor / git status-log-pull)")]
