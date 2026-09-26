import atexit
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

repoRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
scratchRoot = tempfile.mkdtemp(prefix="nemo-repo-plugin-tests-")
atexit.register(shutil.rmtree, scratchRoot, True)

configPath = os.path.join(scratchRoot, "config", "nemo-repo-core.json")
gitConfigPath = os.path.join(scratchRoot, "gitconfig")
open(gitConfigPath, "w").close()

os.environ["NEMO_REPO_CORE_CONFIG"] = configPath
os.environ["NEMO_REPO_LOG"] = "critical"
os.environ["GIT_CONFIG_GLOBAL"] = gitConfigPath
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
os.environ["GIT_AUTHOR_NAME"] = "Test Author"
os.environ["GIT_AUTHOR_EMAIL"] = "author@example.com"
os.environ["GIT_COMMITTER_NAME"] = "Test Author"
os.environ["GIT_COMMITTER_EMAIL"] = "author@example.com"


def _locateCore():
    candidates = [os.environ.get("NEMO_REPO_CORE_PATH"),
                  os.path.join(os.path.dirname(repoRoot), "nemo-repo-core")]
    for candidate in candidates:
        if candidate and os.path.isdir(os.path.join(candidate, "nemoRepoCore")):
            sys.path.insert(0, candidate)
            return


_locateCore()
sys.path.insert(0, repoRoot)

gitAvailable = shutil.which("git") is not None
requiresGit = unittest.skipUnless(gitAvailable, "git is not installed")


def importPlugin(moduleName):
    try:
        import gi
        gi.require_version("Nemo", "3.0")
        return importlib.import_module(moduleName)
    except ValueError as error:
        raise unittest.SkipTest("GObject bindings are missing: %s" % error)
    except ImportError as error:
        if error.name not in ("gi", "nemoRepoCore"):
            raise
        raise unittest.SkipTest(
            "%s is not importable. Install nemo-repo-core, place its checkout next "
            "to this one, or set NEMO_REPO_CORE_PATH." % error.name)


def makeDirectory():
    return tempfile.mkdtemp(dir=scratchRoot)


def runGitCommand(arguments, cwd):
    subprocess.run(["git"] + arguments, cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def writeFile(directory, name, content="content\n"):
    path = os.path.join(directory, name)
    with open(path, "w") as handle:
        handle.write(content)
    return path


def commitFile(repository, name, message="change"):
    writeFile(repository, name, message + "\n")
    runGitCommand(["add", name], repository)
    runGitCommand(["commit", "-q", "-m", message], repository)


def makeRepository(withCommit=True):
    path = makeDirectory()
    runGitCommand(["init", "-q", "-b", "main"], path)
    if withCommit:
        commitFile(path, "readme.txt", "initial commit")
    return path


def makeClonedRepository():
    origin = makeDirectory()
    runGitCommand(["init", "-q", "--bare", "-b", "main"], origin)
    seed = makeRepository()
    runGitCommand(["remote", "add", "origin", origin], seed)
    runGitCommand(["push", "-q", "origin", "main"], seed)
    clone = makeDirectory()
    runGitCommand(["clone", "-q", origin, clone], clone)
    return seed, clone


def makeFakeRepository():
    path = makeDirectory()
    os.mkdir(os.path.join(path, ".git"))
    return path


def writeConfig(config, content):
    os.makedirs(os.path.dirname(config.path), exist_ok=True)
    with open(config.path, "w") as handle:
        json.dump(content, handle)
    config.reload()


def resetSharedState():
    from nemoRepoCore import coreConfig, repoCache
    writeConfig(coreConfig, {})
    repoCache.invalidate()


class FakeNemoFile:

    def __init__(self, path, isDirectory=True, scheme="file"):
        self.path = path
        self.isDirectory = isDirectory
        self.scheme = scheme
        self.emblems = []
        self.attributes = {}
        self.invalidations = 0

    def get_uri_scheme(self):
        return self.scheme

    def get_uri(self):
        from gi.repository import Gio
        if self.scheme != "file":
            return "%s://example.com%s" % (self.scheme, self.path)
        return Gio.File.new_for_path(self.path).get_uri()

    def is_directory(self):
        return self.isDirectory

    def add_emblem(self, name):
        self.emblems.append(name)

    def add_string_attribute(self, name, value):
        self.attributes[name] = value

    def invalidate_extension_info(self):
        self.invalidations += 1
