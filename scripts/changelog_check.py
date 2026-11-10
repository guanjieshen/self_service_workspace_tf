#!/usr/bin/env python3
"""A change to the framework says what it changes: the pull request check behind AGENTS.md's rule
"Keep the guides and the changelog true".

    scripts/changelog_check.py <base ref>        for example: scripts/changelog_check.py origin/main

Lists the files the pull request changes (git diff <base>...HEAD). When it changes framework code
(apps/, bundle/, scripts/, terraform/, install/, .github/, not only their tests) and not
CHANGELOG.md, it fails, saying what to add. It also names the guide in agents/ that describes each
changed part, as a reminder to keep it true (a reminder only: not every change needs one). An
organization's own changes (config/, .github/CODEOWNERS) and docs need no entry.

Only in the framework repository: an organization's copy (it has VERSION) takes the framework's
changes with their entries from a release, so it passes without checking.
"""
import pathlib
import subprocess
import sys

FRAMEWORK = ("apps/", "bundle/", "scripts/", "terraform/", "install/", ".github/")
NOT_CODE = ("/tests/", ".github/CODEOWNERS", ".github/pull_request_template.md")
# The guide that describes each part (agents/*.md), longest prefix first.
GUIDES = [
    ("apps/self-service/db/", "agents/database.md"),
    ("apps/self-service/store.py", "agents/database.md"),
    ("apps/self-service/templates/", "agents/design.md"),
    ("apps/self-service/static/", "agents/design.md"),
    ("apps/", "agents/app.md"),
    ("bundle/", "agents/app.md"),
    ("scripts/app_", "agents/app.md"),
    ("terraform/", "agents/terraform.md"),
    ("config/defaults/", "agents/config.md"),
    ("agents/skills/", "AGENTS.md"),
]


def framework_code(path):
    """Whether a changed file is framework code (its tests and the organization's files are not)."""
    return path.startswith(FRAMEWORK) and not any(part in path for part in NOT_CODE)


def guide_of(path):
    return next((guide for prefix, guide in GUIDES if path.startswith(prefix)), None)


def report(changed):
    """(ok, message) for these changed files."""
    code = sorted(p for p in changed if framework_code(p))
    guides = sorted({g for g in map(guide_of, changed) if g} - set(changed))
    hint = ("\nThe guides that describe what changed, to keep true if it changed what they say: " + ", ".join(guides)) if guides else ""
    if not code or "CHANGELOG.md" in changed:
        return True, ("CHANGELOG.md has an entry for this change." if code else "No framework code changed: no changelog entry needed.") + hint
    return False, ("This pull request changes framework code but not CHANGELOG.md:\n  " + "\n  ".join(code[:20])
                   + ("\n  ..." if len(code) > 20 else "")
                   + "\nAdd an entry under \"## Unreleased\" in CHANGELOG.md: what changed for the people who use it, and what "
                     "the first plan or deploy after it shows (AGENTS.md, \"Keep the guides and the changelog true\")." + hint)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit(__doc__.split("\n\n")[1])
    if (pathlib.Path(__file__).resolve().parent.parent / "VERSION").exists():
        print("An installed copy (VERSION): the changelog is the framework's, nothing to check.")
        return 0
    changed = subprocess.run(["git", "diff", "--name-only", f"{argv[0]}...HEAD"], check=True, capture_output=True, text=True).stdout.split()
    ok, message = report(changed)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
