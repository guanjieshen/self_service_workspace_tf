"""scripts/workspaces.py changed: which workspaces a change plans and applies."""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import SCRIPTS

WORKSPACES = {"alpha": "ci: true", "beta": "ci: true", "local-only": "ci: false", "_example": "ci: true"}


class ChangedWorkspaces(unittest.TestCase):
    def setUp(self):
        self.repo = pathlib.Path(tempfile.mkdtemp())
        (self.repo / "scripts").mkdir()
        shutil.copy(SCRIPTS / "workspaces.py", self.repo / "scripts")
        for name, ci in WORKSPACES.items():
            d = self.repo / "config/workspaces" / name
            d.mkdir(parents=True)
            (d / "workspace.yaml").write_text(f"bu: x\n{ci}\n")
        for f in ["config/defaults/compute.yaml", "terraform/main.tf", "docs/x.md", "README.md"]:
            (self.repo / f).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / f).write_text("v1\n")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        shutil.rmtree(self.repo)

    def git(self, *args):
        return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=self.repo,
                              check=True, capture_output=True, text=True).stdout

    def after_changing(self, *files, plan=False):
        for f in files:
            (self.repo / f).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / f).write_text("v2\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")
        return self.affected(plan)

    def affected(self, plan=False):
        cmd = [sys.executable, str(self.repo / "scripts/workspaces.py"), "changed", *(["--plan"] if plan else []), self.base, "HEAD"]
        out = subprocess.run(cmd, cwd=self.repo, check=True, capture_output=True, text=True).stdout
        return json.loads(out)

    def test_one_workspace(self):
        self.assertEqual(self.after_changing("config/workspaces/alpha/access.yaml"), ["alpha"])

    def test_dev_workspaces_count_like_the_others(self):
        # dev/workspaces/: the workspaces that test the framework itself.
        d = self.repo / "dev/workspaces/gamma"
        d.mkdir(parents=True)
        (d / "workspace.yaml").write_text("bu: x\nci: true\n")
        self.assertEqual(self.after_changing("dev/workspaces/gamma/access.yaml"), ["gamma"])
        self.assertEqual(sorted(self.after_changing("terraform/main.tf")), ["alpha", "beta", "gamma"])

    def test_what_terraform_does_affects_every_ci_workspace(self):
        for f in ["config/defaults/compute.yaml", "terraform/main.tf", "scripts/tf.sh", "scripts/plan-guard.py"]:
            with self.subTest(f=f):
                self.assertEqual(sorted(self.after_changing(f)), ["alpha", "beta"])

    def test_tests_and_other_scripts_affect_nothing(self):
        # A test-only change must not re-apply every workspace (and restart its shared cluster).
        for f in ["terraform/tests/x.tftest.hcl", "scripts/tests/test_x.py", "scripts/workspaces.py new", "scripts/ai-plan-review.py"]:
            with self.subTest(f=f):
                self.assertEqual(self.after_changing(f), [])

    def test_ai_review_changes_plan_every_workspace_but_apply_none(self):
        for f in ["scripts/ai-plan-review.py", ".github/ai/plan-review-prompt.md", "config/setup.yaml", "scripts/preflight.py"]:
            with self.subTest(f=f):
                self.assertEqual(sorted(self.after_changing(f, plan=True)), ["alpha", "beta"])
                self.assertEqual(self.affected(plan=False), [], "the same change applies nothing")

    def test_tests_with_a_workspace_change(self):
        self.assertEqual(self.after_changing("terraform/tests/x.tftest.hcl", "config/workspaces/beta/compute.yaml"), ["beta"])

    def test_docs_affect_nothing(self):
        self.assertEqual(self.after_changing("docs/x.md", "README.md"), [])

    def test_local_only_and_template_folders_are_never_planned(self):
        self.assertEqual(self.after_changing("config/workspaces/local-only/compute.yaml", "config/workspaces/_example/compute.yaml"), [])

    def test_unknown_base_plans_everything(self):
        out = subprocess.run([sys.executable, str(self.repo / "scripts/workspaces.py"), "changed", "0" * 40, "HEAD"], cwd=self.repo,
                             check=True, capture_output=True, text=True).stdout
        self.assertEqual(sorted(json.loads(out)), ["alpha", "beta"])

    def test_all(self):
        out = subprocess.run([sys.executable, str(self.repo / "scripts/workspaces.py"), "changed", "--all"], cwd=self.repo,
                             check=True, capture_output=True, text=True).stdout
        self.assertEqual(sorted(json.loads(out)), ["alpha", "beta"])


if __name__ == "__main__":
    unittest.main()
