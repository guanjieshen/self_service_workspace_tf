#!/usr/bin/env python3
"""Build the release zip an organization installs: this repository without its own environment.

    scripts/release.py <version> [--out dist]     for example: scripts/release.py v1.0.0

The framework repository holds a working installation (its tenant, state storage, account,
workspaces), so that every change is tested for real. A customer must not receive any of it.
From the committed files only (git archive of HEAD), the zip:

  - leaves out dev/, config/backend.hcl and every workspace file but _example.yaml;
  - sets the values in config/setup.yaml to null (the comments stay: they are the instructions);
  - sets account_id in config/defaults/cost.yaml to null;
  - replaces the owners in .github/CODEOWNERS with @your-org/databricks-platform, and on the
    security settings (config/defaults/settings.yaml) with it and @your-org/security;

  - adds VERSION, the release's name (an installation has no tags of this repository);

then refuses to write the zip if any of this repository's identifiers is still in it (its tenant,
subscription, storage, account, workspace hosts and storage roots, CODEOWNERS owners). Run it
from a clean checkout of the commit to release.
"""
import argparse
import io
import pathlib
import re
import subprocess
import sys
import tarfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import workspaces as wsf  # noqa: E402  (the same YAML reading as the other scripts)

LEFT_OUT = re.compile(r"^(dev/|config/backend\.hcl$|config/workspaces/(?!_example\.yaml$)[^/]+\.yaml$)")
# Blanked, but not identifiers: an Azure region is a common word, found in examples too.
NOT_IDENTIFIERS = {"state_location"}
OWNER = "@your-org/databricks-platform"
SECURITY_OWNER = "@your-org/security"
# CODEOWNERS paths that also need the security team (docs/SETUP.md, step 2).
SECURITY_PATHS = ("/config/defaults/settings.yaml",)


def committed_files():
    """path => bytes, for every file committed at HEAD."""
    tar = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", "HEAD"], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        return {m.name: t.extractfile(m).read() for m in t.getmembers() if m.isfile()}


def own_identifiers(files):
    """Values that belong to this repository's environment, to be found nowhere in the zip."""
    found = set()
    setup = files.get("config/setup.yaml", b"").decode()
    for line in setup.splitlines():
        m = re.match(r"^([a-z_]+):\s*(\S+)", line)
        if m and m.group(1) not in NOT_IDENTIFIERS and m.group(2) not in ("null", '""'):
            found.add(m.group(2).strip('"'))
    for value in re.findall(r'=\s*"([^"]+)"', files.get("config/backend.hcl", b"").decode()):
        found.add(value)
    account = re.search(r"(?m)^account_id:\s*([0-9a-f-]{36})", files.get("config/defaults/cost.yaml", b"").decode())
    if account:
        found.add(account.group(1))
    for path, data in files.items():
        if re.match(r"^(config|dev)/workspaces/(?!_example)[^/]+\.yaml$", path):
            text = data.decode()
            found.update(re.findall(r"https://adb-[0-9]+\.[0-9]+\.azuredatabricks\.net", text))
            found.update(re.findall(r"abfss://[^\s\"']+", text))
    found.update(o for o in re.findall(r"@[\w.-]+(?:/[\w.-]+)?", files.get(".github/CODEOWNERS", b"").decode())
                 if o not in (OWNER, SECURITY_OWNER))
    return {v for v in found if len(v) >= 6}


def blank_setup(text):
    """Every value in config/setup.yaml to null, its comment kept."""
    def blank(m):
        key, value, rest = m.group(1), m.group(2), m.group(3) or ""
        if value == "null":
            return m.group(0)
        return f"{key}: null".ljust(len(f"{key}: {value}")) + rest
    return re.sub(r"(?m)^([a-z_]+): (\S+)([ \t]+#.*)?$", blank, text)


def release_files(files):
    out = {}
    for path, data in files.items():
        if LEFT_OUT.match(path):
            continue
        if path == "config/setup.yaml":
            data = blank_setup(data.decode()).encode()
        elif path == "config/defaults/cost.yaml":
            data = re.sub(r"(?m)^account_id: .*$", "account_id: null   # the Databricks account ID (account console, top right)",
                          data.decode()).encode()
        elif path == ".github/CODEOWNERS":
            data = release_codeowners(data.decode()).encode()
        out[path] = data
    return out


def release_codeowners(text):
    """Every owner to OWNER; the security paths' owners to OWNER and SECURITY_OWNER."""
    lines = []
    for line in text.splitlines():
        if line.split()[:1] and line.split()[0] in SECURITY_PATHS:
            line = line.split()[0].ljust(len(line) - len(line.lstrip()) + 36) + f"{OWNER} {SECURITY_OWNER}"
        else:
            for owner in set(re.findall(r"@[\w.-]+(?:/[\w.-]+)?", line)) - {OWNER, SECURITY_OWNER}:
                line = re.sub(rf"{re.escape(owner)}(?![\w/.-])", OWNER, line)
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def leaks(files, identifiers):
    """[(path, identifier)] still in the release."""
    out = []
    for path, data in files.items():
        try:
            text = data.decode()
        except UnicodeDecodeError:
            continue
        out.extend((path, i) for i in sorted(identifiers) if i in text)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("version", help="the release's name, for example v1.0.0")
    ap.add_argument("--out", default=str(ROOT / "dist"), help="folder for the zip (default: dist/)")
    args = ap.parse_args(argv)
    if not re.fullmatch(r"v\d+\.\d+\.\d+", args.version):
        raise SystemExit(f"version must look like v1.0.0, not {args.version!r}")
    files = committed_files()
    release = release_files(files)
    # Which release an installation runs: git init after unzipping has no tags.
    release["VERSION"] = (args.version + "\n").encode()
    found = leaks(release, own_identifiers(files))
    if found:
        for path, value in found:
            print(f"error: {path} still contains {value!r}, which belongs to this repository's environment", file=sys.stderr)
        return 1
    name = f"{ROOT.name}-{args.version}"
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    zip_path = out / f"{name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(release):
            info = zipfile.ZipInfo(f"{name}/{path}")
            info.external_attr = (0o755 if path.endswith((".sh", ".py")) and path.startswith("scripts/") else 0o644) << 16
            z.writestr(info, release[path])
    print(f"{zip_path}: {len(release)} files (left out: {len(files) - len(release)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
