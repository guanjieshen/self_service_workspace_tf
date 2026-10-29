"""A setting left alone (null) is released (removed from the state) instead of destroyed.

Destroying a setting resets it: the workspace_conf provider erases removed keys, a deleted
setting goes back to the platform default, and deleting the users group's entitlements
removes them from everyone. So terraform/overrides.tf maps each setting to what it owns,
and scripts/tf.sh removes those addresses from the state before apply.
"""
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

from helpers import ROOT, SCRIPTS

TF = ROOT / "terraform"


def address_maps():
    """path => addresses, from setting_addresses and switch_addresses in terraform/overrides.tf."""
    text = (TF / "overrides.tf").read_text()
    subs = {name: re.search(rf'^\s*{name}\s*=\s*"([^"]+)"', text, re.M).group(1) for name in ("ws", "wsc")}
    out = {}
    for name in ("setting_addresses", "switch_addresses"):
        block = re.search(rf"{name} = \{{\n(.*?)\n  \}}", text, re.S).group(1)
        for line in block.splitlines():
            m = re.match(r'\s*"([\w.]+)"\s*=\s*\[(.*)\]\s*$', line)
            if m:
                addrs = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(2))
                out[m.group(1)] = [re.sub(r"\$\{local\.(\w+)\}", lambda x: subs[x.group(1)], a).replace('\\"', '"') for a in addrs]
    return out


def module_dirs():
    """Module name in the root => its folder."""
    main = (TF / "main.tf").read_text()
    return {m.group(1): TF / m.group(2) for m in re.finditer(r'module "([\w-]+)" \{\s*source\s*=\s*"\./([^"]+)"', main)}


def default_keys(path):
    """Whether a dotted path (section.key[.key]) is in config/defaults/."""
    parts = path.split(".")
    for f in (ROOT / "config/defaults").glob("*.yaml"):
        lines = [l for l in f.read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")]
        try:
            i = lines.index(next(l for l in lines if re.match(rf"^{parts[0]}:", l)))
        except StopIteration:
            continue
        block = []
        for l in lines[i + 1:]:
            if not l.startswith(" "):
                break
            block.append(l)
        if not re.search(rf"^  {parts[1]}:", "\n".join(block), re.M):
            continue
        if len(parts) == 2:
            return True
        j = next(n for n, l in enumerate(block) if re.match(rf"^  {parts[1]}:", l))
        sub = []
        for l in block[j + 1:]:
            if not l.startswith("    "):
                break
            sub.append(l)
        return bool(re.search(rf"^    {parts[2]}:", "\n".join(sub), re.M))
    return False


class ReleaseMap(unittest.TestCase):
    def test_every_path_is_a_baseline_key(self):
        for path in address_maps():
            with self.subTest(path=path):
                self.assertTrue(default_keys(path), f"{path} is not a key in config/defaults/")

    def test_every_address_is_a_real_resource_or_module(self):
        dirs = module_dirs()
        for path, addrs in address_maps().items():
            for addr in addrs:
                with self.subTest(path=path, addr=addr):
                    m = re.fullmatch(r'module\.([\w-]+)(?:\[0\])?(?:\.(\w+)\.(\w+)(?:\[.*\])?)?', addr)
                    self.assertIsNotNone(m, f"unexpected address shape {addr}")
                    module, rtype, rname = m.groups()
                    self.assertIn(module, dirs, f"no module {module}")
                    if rtype:
                        src = "\n".join(f.read_text() for f in dirs[module].glob("*.tf"))
                        self.assertTrue(re.search(rf'resource "{rtype}" "{rname}"', src), f"{addr}: no such resource in {dirs[module]}")

    def test_workspace_conf_keys_match_the_module(self):
        # Each workspace configuration key the module sets must be released by some setting,
        # or leaving that setting alone would destroy (reset) it.
        src = (TF / "modules/workspace-settings/main.tf").read_text()
        keys = set(re.findall(r"^\s{4}(\w+)\s+= ", re.search(r"conf_candidates = \{(.*?)\n  \}", src, re.S).group(1), re.M))
        released = {re.search(r'\["(\w+)"\]', a).group(1) for addrs in address_maps().values()
                    for a in addrs if "databricks_workspace_conf" in a}
        self.assertEqual(released, keys)


FAKE_TERRAFORM = r'''#!/usr/bin/env python3
"""Stands in for terraform: logs each call, answers from files in $FAKE_DIR."""
import os, sys, pathlib
d = pathlib.Path(os.environ["FAKE_DIR"])
args = [a for a in sys.argv[1:] if not a.startswith("-chdir")]
with open(d / "calls.log", "a") as f:
    f.write(" ".join(args) + "\n")
released = (d / "released.log").exists()
if args[:2] == ["state", "list"]:
    print((d / "state.txt").read_text(), end="")
elif args[:2] == ["state", "rm"]:
    with open(d / "released.log", "a") as f:
        f.write(args[2] + "\n")
elif args[0] == "show" and "-json" in args:
    print((d / ("plan-after.json" if released else "plan.json")).read_text())
elif args[0] == "show":
    print("plan text")
'''


class TfShRelease(unittest.TestCase):
    """scripts/tf.sh apply, with a stand-in terraform."""

    def setUp(self):
        self.repo = pathlib.Path(tempfile.mkdtemp())
        (self.repo / "scripts").mkdir()
        for f in ("tf.sh", "plan-guard.py"):
            shutil.copy(SCRIPTS / f, self.repo / "scripts")
        (self.repo / "terraform").mkdir()
        (self.repo / "config/workspaces").mkdir(parents=True)
        (self.repo / "config/workspaces/ws.yaml").write_text("bu: x\n")
        self.fake = self.repo / "fake"
        self.fake.mkdir()
        tf = self.fake / "terraform"
        tf.write_text(FAKE_TERRAFORM)
        tf.chmod(tf.stat().st_mode | stat.S_IEXEC)

    def tearDown(self):
        shutil.rmtree(self.repo)

    def plan(self, deletes, released):
        return json.dumps({
            "resource_changes": [{"address": a, "mode": "managed", "type": a.split(".")[-2].split("[")[0], "name": "x",
                                  "change": {"actions": ["delete"], "before": {}, "after": None}} for a in deletes],
            "planned_values": {"outputs": {"released_addresses": {"value": released}}},
        })

    def apply(self, state, plan, plan_after):
        (self.fake / "state.txt").write_text("\n".join(state) + "\n")
        (self.fake / "plan.json").write_text(plan)
        (self.fake / "plan-after.json").write_text(plan_after)
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
        env.update(TERRAFORM=str(self.fake / "terraform"), FAKE_DIR=str(self.fake), CONFIRM_ENV="ws", ALLOW_LOCAL_APPLY="1")
        out = subprocess.run([str(self.repo / "scripts/tf.sh"), "ws", "apply"], env=env, stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=60)
        calls = (self.fake / "calls.log").read_text().splitlines()
        released = (self.fake / "released.log").read_text().split() if (self.fake / "released.log").exists() else []
        return out, calls, released

    def test_released_resources_leave_the_state_before_apply(self):
        users = "module.personas.databricks_entitlements.users[0]"
        pat = 'module.workspace_settings.databricks_workspace_conf.key["enableTokensConfig"]'
        folder = 'module.folders.databricks_directory.team["a"]'
        prefixes = ["module.personas.databricks_entitlements.users", pat]
        out, calls, released = self.apply(
            state=[users, pat, folder],
            plan=self.plan([users, pat], prefixes),
            plan_after=self.plan([], prefixes))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(sorted(released), sorted([users, pat]))
        self.assertNotIn(folder, released)
        applies = [i for i, c in enumerate(calls) if c.startswith("apply")]
        removes = [i for i, c in enumerate(calls) if c.startswith("state rm")]
        self.assertEqual(len(applies), 1)
        self.assertLess(max(removes), applies[0], "released before the apply")
        self.assertEqual(sum(c.startswith("plan") for c in calls), 2, "planned again after releasing")

    def test_nothing_released_means_one_plan_and_no_state_change(self):
        out, calls, released = self.apply(state=["a.b"], plan=self.plan([], []), plan_after=self.plan([], []))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(released, [])
        self.assertEqual(sum(c.startswith("plan") for c in calls), 1)

    def test_a_delete_that_is_not_released_still_needs_confirmation(self):
        folder = 'module.folders.databricks_directory.team["a"]'
        (self.fake / "state.txt").write_text(folder + "\n")
        (self.fake / "plan.json").write_text(self.plan([folder], ["module.personas.databricks_entitlements.users"]))
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_ACTIONS", "CONFIRM_ENV")}
        env.update(TERRAFORM=str(self.fake / "terraform"), FAKE_DIR=str(self.fake), ALLOW_LOCAL_APPLY="1")
        out = subprocess.run([str(self.repo / "scripts/tf.sh"), "ws", "apply"], env=env, stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=60)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("Refusing to apply risky changes", out.stdout + out.stderr)
        self.assertFalse(any(c.startswith("apply") for c in (self.fake / "calls.log").read_text().splitlines()))

    def test_apply_and_destroy_refuse_outside_github_actions(self):
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_ACTIONS", "ALLOW_LOCAL_APPLY")}
        env.update(TERRAFORM=str(self.fake / "terraform"), FAKE_DIR=str(self.fake), CONFIRM_ENV="ws")
        for cmd in ("apply", "destroy"):
            out = subprocess.run([str(self.repo / "scripts/tf.sh"), "ws", cmd], env=env, stdin=subprocess.DEVNULL,
                                 capture_output=True, text=True, timeout=60)
            self.assertNotEqual(out.returncode, 0, cmd)
            self.assertIn(f"Refusing to {cmd} outside GitHub Actions", out.stdout)
            self.assertFalse((self.fake / "calls.log").exists(), f"{cmd}: terraform was not run")


if __name__ == "__main__":
    unittest.main()
