# Databricks notebook source
# MAGIC %md
# MAGIC # Copy the workspace baseline into your repository
# MAGIC
# MAGIC For installing from Databricks, with nothing to run on a laptop ([docs/SETUP.md](../docs/SETUP.md), step 2).
# MAGIC It copies this repository from one Databricks **Git folder** into another: your organization's
# MAGIC repository, which may already hold files from its template.
# MAGIC
# MAGIC | Widget | Value |
# MAGIC | --- | --- |
# MAGIC | `source` | The Git folder of this repository (`main`, or a `release/<version>` branch) |
# MAGIC | `target` | The Git folder of your repository, on a **new branch** |
# MAGIC | `mode` | `preview` (the default) lists what would change and writes nothing; `copy` writes it |
# MAGIC
# MAGIC **This repository's own environment is never copied:** its workspace files, its `config/backend.hcl`
# MAGIC and `dev/`, and the values in `config/setup.yaml`, `config/self-service/hub.yaml` and
# MAGIC `.github/CODEOWNERS` (the same rules as a release, `scripts/release.py`). If any of its identifiers
# MAGIC would still be copied, it stops and writes nothing.
# MAGIC
# MAGIC It checks every file before it writes any, and never deletes a file of yours. A file that exists in both is replaced by this one's, except
# MAGIC `.gitignore`, where your lines are kept too. Your old `.github/CODEOWNERS` is printed, to merge by hand.
# MAGIC Then, in the target Git folder: **Commit & push**, and open a pull request on GitHub.
# MAGIC
# MAGIC **From a terminal** (the Databricks web terminal, for example, after `git clone` of this repository)
# MAGIC the same copy is one command, instead of `cp`:
# MAGIC `python3 install/copy_to_your_repo.py <this repository's folder> <your repository's folder> [--copy]`
# MAGIC (without `--copy` it previews).

# COMMAND ----------

import argparse
import fnmatch
import importlib.util
import os
import pathlib
import sys

# Merged instead of replaced: this release's lines, then the target's that are not in it.
MERGED = {".gitignore"}
# Your configuration: on an upgrade (the target already has VERSION), an existing file here is
# yours and is kept; the framework's files under config/ are not (they are replaced).
YOURS = ("config/", ".github/CODEOWNERS")
FRAMEWORK_CONFIG = {"config/README.md", "config/AGENTS.md", "config/workspaces/_example.yaml"}
# Folders that hold only framework files: on an upgrade, a file there that the new version no
# longer has is removed (your own files elsewhere, your workflows for example, are never touched).
FRAMEWORK_DIRS = ("agents/", "apps/", "bundle/", "docs/", "install/", "scripts/", "terraform/",
                  ".github/actions/", ".github/ai/", ".github/scripts/")
# Replaced, but shown first: the target's version may hold rules its organization requires.
SHOWN = {".github/CODEOWNERS"}


def files(root):
    """Relative paths of every file under root, without git's own (a .git folder, or the .git file
    of a worktree or submodule)."""
    root = pathlib.Path(root)
    out = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            if name != ".git":
                out.add((pathlib.Path(dirpath) / name).relative_to(root).as_posix())
    return out


def ignored(root):
    """A test for paths git ignores in root (its .gitignore files: names, dir/ and *.ext patterns,
    the forms this repository uses), so build outputs and local state are never copied."""
    root, rules = pathlib.Path(root), []
    for path in files(root):
        if path == ".gitignore" or path.endswith("/.gitignore"):
            base = path.rpartition("/")[0]
            for line in (root / path).read_text().splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "!")):
                    rules.append((base, line))

    def test(path):
        for base, rule in rules:
            if base and not path.startswith(base + "/"):
                continue
            rel = path[len(base) + 1:] if base else path
            parts = rel.split("/")
            if rule.endswith("/"):
                if rule[:-1] in parts[:-1] or "/".join(parts[:-1]).startswith(rule[:-1] + "/") or rel.startswith(rule):
                    return True
            elif "/" in rule.strip("/"):
                if fnmatch.fnmatch(rel, rule.strip("/")):
                    return True
            elif any(fnmatch.fnmatch(part, rule) for part in parts):
                return True
        return False
    return test


def readable(path):
    """Whether a file can be copied as bytes. A notebook in a Git folder (this one, for example)
    cannot: it is a workspace object, read through /Workspace without its extension."""
    try:
        with open(path, "rb") as f:
            f.read(1)
        return True
    except OSError:
        return False


def check(source, target):
    """Problems with the two paths, as messages (none: go ahead)."""
    source, target = pathlib.Path(source).resolve(), pathlib.Path(target).resolve()
    problems = []
    if not (source / "scripts/release.py").is_file() or not (source / "scripts/tf.sh").is_file():
        problems.append(f"{source} is not this repository: give the Git folder you cloned it into")
    if not target.is_dir():
        problems.append(f"{target} does not exist: create a Git folder for your repository first")
    if source == target or source in target.parents or target in source.parents:
        problems.append("source and target must be two separate Git folders")
    return problems


def source_version(source):
    """What VERSION says when the source is not a release: its branch and commit, from git's
    own files when they can be read (a clone in the web terminal), else just "main"."""
    git = pathlib.Path(source) / ".git"
    try:
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref: "):
            return f"main @ {head[:7]}"   # a detached checkout: the commit itself
        ref = head[5:]
        loose = git / ref
        sha = loose.read_text().strip() if loose.is_file() else next(
            line.split()[0] for line in (git / "packed-refs").read_text().splitlines() if line.endswith(" " + ref))
        return f"{ref.rpartition('/')[2]} @ {sha[:7]}"
    except (OSError, StopIteration):   # a Databricks Git folder does not show .git
        return "main"


def released(source):
    """{path: bytes}: what is copied. Every readable file of the source, as a release has it
    (scripts/release.py: this repository's environment left out or blanked), with VERSION
    (a release's, or the source's branch and commit: source_version). ValueError if any of the source's own
    identifiers is still in it: then nothing is copied."""
    source = pathlib.Path(source)
    spec = importlib.util.spec_from_file_location("release", source / "scripts/release.py")
    rel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rel)
    skip = ignored(source)
    found = {p: (source / p).read_bytes() for p in files(source) if not skip(p) and readable(source / p)}
    out = rel.release_files(found)
    out.setdefault("VERSION", (source_version(source) + "\n").encode())
    leaked = rel.leaks(out, rel.own_identifiers(found))
    if leaked:
        raise ValueError("This repository's own identifiers would be copied; nothing was written:\n"
                         + "\n".join(f"  {path}: {value}" for path, value in leaked))
    return out


KEPT = "# Kept from your repository"


def merged_lines(ours, theirs):
    """This release's lines, then the target's that are not in it (the same result when run again)."""
    extra = [l for l in theirs.splitlines() if l.strip() and l != KEPT and l not in ours.splitlines()]
    return ours if not extra else ours.rstrip("\n") + f"\n\n{KEPT}\n" + "\n".join(extra) + "\n"


def yours(path):
    return path.startswith(YOURS) and path not in FRAMEWORK_CONFIG


def plan(source, target, release):
    """{path: action} for every file: new, same, replace, merge (ours), keep (theirs only), skip
    (ours, but a notebook or this repository's environment: not copied). On an upgrade (the
    target has VERSION) also: yours (your configuration, kept) and remove (a framework file the
    new version no longer has). release: released(source). Every file is checked here, so the
    copy cannot stop half-way."""
    source, target = pathlib.Path(source), pathlib.Path(target)
    skip = ignored(source)   # build outputs and local state: not part of the repository, not listed
    ours, theirs = {p for p in files(source) if not skip(p)} | set(release), files(target)
    upgrade, local = (target / "VERSION").is_file(), ignored(target)
    out = {}
    for path in sorted(ours | theirs):
        if path not in ours:
            out[path] = "remove" if upgrade and path.startswith(FRAMEWORK_DIRS) and not local(path) else "keep"
        elif upgrade and path in theirs and yours(path) and release.get(path) != (target / path).read_bytes():
            out[path] = "yours"
        elif upgrade and path not in theirs and path.startswith("config/defaults/"):
            out[path] = "baseline"   # a new baseline file would turn its settings on: yours to add
        elif path not in release:   # a notebook (this installer), or this repository's environment
            out[path] = "keep" if path in theirs else "skip"   # a file of theirs with the same name stays theirs
        elif path not in theirs:
            out[path] = "new"
        elif release[path] == (target / path).read_bytes():
            out[path] = "same"
        elif path in MERGED:
            theirs_text = (target / path).read_text()
            out[path] = "same" if merged_lines(release[path].decode(), theirs_text) == theirs_text else "merge"
        else:
            out[path] = "replace"
    return out


def report(actions, target):
    """What preview shows: a count per action, then every file that is not simply new."""
    counts = {a: sum(1 for v in actions.values() if v == a) for a in ("new", "same", "replace", "merge", "keep", "skip", "yours", "remove", "baseline")}
    lines = ["  ".join(f"{a}: {n}" for a, n in counts.items() if n or a in ("new", "same"))]
    for path, action in actions.items():
        if action in ("replace", "merge", "keep", "skip", "remove", "baseline"):
            lines.append(f"  {action:8} {path}")
    if "yours" in actions.values():
        lines.append("Kept as yours (an upgrade): your configuration under config/ and .github/CODEOWNERS. "
                     "CHANGELOG.md's Baseline edits list what to change in it by hand.")
    if "baseline" in actions.values():
        lines.append("Not copied (baseline): new files in config/defaults/; add them yourself if you want their settings "
                     "(an upgrade never turns a setting on by itself).")
    if "skip" in actions.values():
        lines.append("Skipped: notebooks (this installer) and this repository's own environment; your repository needs neither.")
    workflows = [p for p, a in actions.items() if a == "keep" and p.startswith(".github/workflows/")]
    if workflows:
        lines.append("Your repository's own workflows stay and keep running on pull requests: " + ", ".join(workflows))
    for path in sorted(SHOWN):
        if actions.get(path) == "replace":
            lines.append(f"Your {path}, replaced; merge any owners your organization requires into the new one:\n"
                         + (pathlib.Path(target) / path).read_text())
    return "\n".join(lines)


def copy(target, actions, release):
    """Write the release into the target, as planned. Returns the number of files written."""
    target = pathlib.Path(target)
    written = 0
    for path, action in actions.items():
        if action in ("new", "replace"):
            (target / path).parent.mkdir(parents=True, exist_ok=True)
            (target / path).write_bytes(release[path])
            if release[path].startswith(b"#!"):   # a script stays runnable (scripts/tf.sh)
                (target / path).chmod((target / path).stat().st_mode | 0o111)
            written += 1
        elif action == "merge":
            (target / path).write_text(merged_lines(release[path].decode(), (target / path).read_text()))
            written += 1
        elif action == "remove":
            (target / path).unlink()
            written += 1
    return written

# COMMAND ----------

def run(source, target, write):
    """Check, plan, report, and copy when write is True: what both the notebook and the command do."""
    problems = check(source, target)
    if problems:
        raise ValueError("\n".join(problems))
    release = released(source)
    actions = plan(source, target, release)
    print(report(actions, target))
    if write:
        print(f"\nWrote {copy(target, actions, release)} files. Now, in the target repository: commit and push a branch, then open a pull request.")
    else:
        print("\nPreview only: nothing was written. Run again to copy (mode: copy, or --copy).")


# A command when given the two folders (a terminal, or a Python file task, where dbutils exists too);
# otherwise, in a notebook, its widgets. A notebook's own arguments start with "-" (the kernel's).
COMMAND = __name__ == "__main__" and len(sys.argv) > 2 and not sys.argv[1].startswith("-")

if COMMAND:
    args = argparse.ArgumentParser(description="Copy this repository into yours, without its own environment.")
    args.add_argument("source", help="this repository's folder (a clone of main, or a release)")
    args.add_argument("target", help="your repository's folder, on a new branch")
    args.add_argument("--copy", action="store_true", help="write the files (without it: preview only)")
    a = args.parse_args()
    try:
        run(a.source, a.target, a.copy)
    except ValueError as e:
        sys.exit(str(e))
elif "dbutils" in globals():
    dbutils.widgets.text("source", "", "Git folder of this repository (cloned)")
    dbutils.widgets.text("target", "", "Git folder of your repository (a new branch)")
    dbutils.widgets.dropdown("mode", "preview", ["preview", "copy"], "preview writes nothing")
    source, target, mode = (dbutils.widgets.get(k).strip() for k in ("source", "target", "mode"))
    for path in (source, target):
        if path and not path.startswith("/Workspace/"):
            raise ValueError(f"{path}: give the full path, starting with /Workspace/ (the Git folder's Copy path)")
    run(source, target, mode == "copy")
