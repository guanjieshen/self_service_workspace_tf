"""The docs and comments point at files that exist.

Someone new follows the paths they read. A workspace is one file
(config/workspaces/<name>.yaml), so "its settings.yaml" or a path that was renamed sends
them looking for something that is not there.
"""
import re
import subprocess
import unittest

from helpers import ROOT

PATH = re.compile(r"(?<![\w./-])((?:config|docs|scripts|terraform|agents|\.github)/[A-Za-z0-9_./-]*[A-Za-z0-9_/])")
# A baseline file named on its own reads as the workspace's own file, which does not exist.
BARE_BASELINE = re.compile(r"(?<![\w/.-])(access|compute|cost|catalog|settings)\.yaml")
GENERATED = {"config/backend.hcl"}           # written by scripts/setup.py
EXAMPLE_WORKSPACE = re.compile(r"config/workspaces/[a-z0-9-]+\.yaml")  # a workspace in an example
SKIP = {"CHANGELOG.md"}                       # history: it names what was removed


def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / f for f in out.splitlines()]


def text_lines(path):
    """(line number, text) of the lines a reader reads: all of a doc, the comments of code and YAML."""
    lines = path.read_text().splitlines()
    if path.suffix == ".md":
        return enumerate(lines, 1)
    marker = "//" if path.suffix == ".js" else "#"
    return ((n, l[l.index(marker):]) for n, l in enumerate(lines, 1) if marker in l)


def files():
    return [p for p in tracked() if p.exists() and p.name not in SKIP and "/tests/fixtures/" not in str(p)
            and p.suffix in (".md", ".yaml", ".yml", ".tf", ".hcl", ".py", ".sh", ".js")]


class Docs(unittest.TestCase):
    maxDiff = None

    def test_paths_exist(self):
        missing = []
        for path in files():
            for n, line in text_lines(path):
                for ref in PATH.findall(line):
                    if "<" in ref or ref in GENERATED or EXAMPLE_WORKSPACE.fullmatch(ref):
                        continue
                    if not (ROOT / ref).exists():
                        missing.append(f"{path.relative_to(ROOT)}:{n}: {ref}")
        self.assertEqual(missing, [], "paths that do not exist")

    def test_baseline_files_are_named_with_their_folder(self):
        bare = []
        for path in files():
            if path.parent.name == "defaults" and path.suffix == ".yaml":
                continue                           # a baseline file naming a sibling
            for n, line in text_lines(path):
                if any(c in line for c in "│├└"):  # a folder tree
                    continue
                for m in BARE_BASELINE.finditer(line):
                    if not line[:m.start()].endswith("defaults/"):
                        bare.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:100]}")
        self.assertEqual(bare, [], "say config/defaults/<file>.yaml, or the workspace's file")


if __name__ == "__main__":
    unittest.main()
