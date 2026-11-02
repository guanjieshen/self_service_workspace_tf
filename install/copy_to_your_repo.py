# Databricks notebook source
# MAGIC %md
# MAGIC # Copy the workspace baseline into your repository
# MAGIC
# MAGIC For installing without git on a laptop ([docs/SETUP.md](../docs/SETUP.md), step 2). It copies this
# MAGIC release from one Databricks **Git folder** into another: your organization's repository, which may
# MAGIC already hold files from its template.
# MAGIC
# MAGIC | Widget | Value |
# MAGIC | --- | --- |
# MAGIC | `source` | The Git folder of this repository, on the branch `release/<version>` (it holds `VERSION`) |
# MAGIC | `target` | The Git folder of your repository, on a **new branch** |
# MAGIC | `mode` | `preview` (the default) lists what would change and writes nothing; `copy` writes it |
# MAGIC
# MAGIC It checks every file before it writes any, and never deletes a file of yours. A file that exists in both is replaced by this release's, except
# MAGIC `.gitignore`, where your lines are kept too. Your old `.github/CODEOWNERS` is printed, to merge by hand.
# MAGIC Then, in the target Git folder: **Commit & push**, and open a pull request on GitHub.

# COMMAND ----------

import os
import pathlib
import shutil

# Merged instead of replaced: this release's lines, then the target's that are not in it.
MERGED = {".gitignore"}
# Replaced, but shown first: the target's version may hold rules its organization requires.
SHOWN = {".github/CODEOWNERS"}


def files(root):
    """Relative paths of every file under root, without git's own folder."""
    root = pathlib.Path(root)
    out = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            out.add((pathlib.Path(dirpath) / name).relative_to(root).as_posix())
    return out


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
    if not (source / "VERSION").is_file() or not (source / "scripts/tf.sh").is_file():
        problems.append(f"{source} is not this release: check out the branch release/<version> there (it holds VERSION)")
    if not target.is_dir():
        problems.append(f"{target} does not exist: create a Git folder for your repository first")
    if source == target or source in target.parents or target in source.parents:
        problems.append("source and target must be two separate Git folders")
    return problems


KEPT = "# Kept from your repository"


def merged_lines(ours, theirs):
    """This release's lines, then the target's that are not in it (the same result when run again)."""
    extra = [l for l in theirs.splitlines() if l.strip() and l != KEPT and l not in ours.splitlines()]
    return ours if not extra else ours.rstrip("\n") + f"\n\n{KEPT}\n" + "\n".join(extra) + "\n"


def plan(source, target):
    """{path: action} for every file: new, same, replace, merge (ours), keep (theirs only), skip
    (ours, but a notebook: not copied). Every file is checked here, so the copy cannot stop half-way."""
    source, target = pathlib.Path(source), pathlib.Path(target)
    ours, theirs = files(source), files(target)
    out = {}
    for path in sorted(ours | theirs):
        if path not in ours:
            out[path] = "keep"
        elif not readable(source / path):
            out[path] = "skip"
        elif path not in theirs:
            out[path] = "new"
        elif (source / path).read_bytes() == (target / path).read_bytes():
            out[path] = "same"
        elif path in MERGED:
            theirs_text = (target / path).read_text()
            out[path] = "same" if merged_lines((source / path).read_text(), theirs_text) == theirs_text else "merge"
        else:
            out[path] = "replace"
    return out


def report(actions, target):
    """What preview shows: a count per action, then every file that is not simply new."""
    counts = {a: sum(1 for v in actions.values() if v == a) for a in ("new", "same", "replace", "merge", "keep", "skip")}
    lines = ["  ".join(f"{a}: {n}" for a, n in counts.items())]
    for path, action in actions.items():
        if action in ("replace", "merge", "keep", "skip"):
            lines.append(f"  {action:8} {path}")
    if "skip" in actions.values():
        lines.append("Skipped: notebooks (this installer); your repository does not need them.")
    workflows = [p for p, a in actions.items() if a == "keep" and p.startswith(".github/workflows/")]
    if workflows:
        lines.append("Your repository's own workflows stay and keep running on pull requests: " + ", ".join(workflows))
    for path in sorted(SHOWN):
        if actions.get(path) == "replace":
            lines.append(f"Your {path}, replaced; merge any owners your organization requires into the new one:\n"
                         + (pathlib.Path(target) / path).read_text())
    return "\n".join(lines)


def copy(source, target, actions):
    """Write the release into the target, as planned. Returns the number of files written."""
    source, target = pathlib.Path(source), pathlib.Path(target)
    written = 0
    for path, action in actions.items():
        if action in ("new", "replace"):
            (target / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / path, target / path)
            written += 1
        elif action == "merge":
            (target / path).write_text(merged_lines((source / path).read_text(), (target / path).read_text()))
            written += 1
    return written

# COMMAND ----------

if "dbutils" in globals():
    dbutils.widgets.text("source", "", "Git folder of this release (release/<version>)")
    dbutils.widgets.text("target", "", "Git folder of your repository (a new branch)")
    dbutils.widgets.dropdown("mode", "preview", ["preview", "copy"], "preview writes nothing")
    source, target, mode = (dbutils.widgets.get(k).strip() for k in ("source", "target", "mode"))
    for path in (source, target):
        if path and not path.startswith("/Workspace/"):
            raise ValueError(f"{path}: give the full path, starting with /Workspace/ (the Git folder's Copy path)")
    problems = check(source, target)
    if problems:
        raise ValueError("\n".join(problems))
    actions = plan(source, target)
    print(report(actions, target))
    if mode == "copy":
        print(f"\nWrote {copy(source, target, actions)} files. Now, in the target Git folder: Commit & push, then open a pull request.")
    else:
        print("\nPreview only: nothing was written. Set mode to copy and run again.")
