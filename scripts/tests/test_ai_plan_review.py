"""scripts/ai-plan-review.py: settings, what the reviewer is shown, and reading the answer."""
import base64
import contextlib
import io
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ROOT, SCRIPTS, change, load

review = load("ai-plan-review")


class Settings(unittest.TestCase):
    """config/setup.yaml: ai_review_host turns the review on; the model there reviews every plan."""

    HOST = "https://adb-1234567890123456.7.azuredatabricks.net"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = review.ROOT
        review.ROOT = pathlib.Path(self.tmp.name)
        (review.ROOT / "config").mkdir()

    def tearDown(self):
        review.ROOT = self.orig
        self.tmp.cleanup()

    def setup_yaml(self, text):
        (review.ROOT / "config/setup.yaml").write_text(text)

    def test_off_without_a_review_host(self):
        self.setup_yaml("ai_review_host: null   # none\nai_review_model: null\n")
        self.assertFalse(review.load_settings()["enabled"])
        (review.ROOT / "config/setup.yaml").unlink()
        self.assertFalse(review.load_settings()["enabled"], "no setup file: no review")

    def test_the_review_host_and_its_model(self):
        self.setup_yaml(f"ai_review_host: {self.HOST}/   # the model's workspace\nai_review_model: null\n")
        s = review.load_settings()
        self.assertEqual((s["enabled"], s["host"], s["endpoint"]), (True, self.HOST, "system.ai.claude-sonnet-5-5"))
        self.setup_yaml(f"ai_review_host: {self.HOST}\nai_review_model: \"system.ai.claude-haiku-5-5\"\n")
        self.assertEqual(review.load_settings()["label"], "system.ai.claude-haiku-5-5")

    def test_a_custom_url_is_refused(self):
        # A custom workspace URL serves the web page, not the API.
        self.setup_yaml("ai_review_host: https://myorg.azuredatabricks.net\n")
        with self.assertRaises(ValueError):
            review.load_settings()

    def test_a_wrong_review_host_turns_the_review_off_not_the_plan(self):
        self.setup_yaml("ai_review_host: https://myorg.azuredatabricks.net\n")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["ai-plan-review.py", "--settings"]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(review.main(), 0)
        self.assertIn("enabled=false", out.getvalue())
        self.assertIn("AI review off", err.getvalue())

    def test_the_shipped_prompt_exists(self):
        self.assertTrue((self.orig / review.PROMPT).exists())

    def test_the_setup_file_names_both_values(self):
        text = (self.orig / "config/setup.yaml").read_text()
        self.assertRegex(text, r"(?m)^ai_review_host:")
        self.assertRegex(text, r"(?m)^ai_review_model:")


class PlannedChanges(unittest.TestCase):
    def test_actions_and_skipped_entries(self):
        plan = {"resource_changes": [
            change("databricks_sql_endpoint", ["create"], after={"name": "W", "cluster_size": "Small"}),
            change("databricks_sql_endpoint", ["update"], before={"name": "W", "cluster_size": "Small"}, after={"name": "W", "cluster_size": "Medium"}),
            change("databricks_directory", ["delete"], before={"path": "/Shared/X"}),
            change("databricks_cluster", ["delete", "create"], before={"cluster_name": "a"}, after={"cluster_name": "a"}),
            change("databricks_sql_endpoint", ["no-op"]),
            change("terraform_data", ["create"], after={}),
            {**change("databricks_group", ["read"]), "mode": "data"},
        ]}
        got = review.planned_changes(plan)
        self.assertEqual([c["action"] for c in got], ["create", "update", "delete", "replace"])
        self.assertEqual(got[0]["kind"], "SQL warehouse")
        self.assertEqual(got[1]["changed"], {"cluster_size": {"before": "Small", "after": "Medium"}})
        self.assertEqual(got[2]["name"], "/Shared/X")

    def test_noise_removed_and_files_decoded(self):
        after = {"id": "1", "path": "/x.md", "content_base64": base64.b64encode(b"hello").decode(), "md5": "m",
                 "definition": json.dumps({"a": 1, "b": None})}
        got = review.planned_changes({"resource_changes": [change("databricks_workspace_file", ["create"], after=after)]})
        self.assertEqual(got[0]["after"], {"path": "/x.md", "content": "hello", "definition": {"a": 1}})


class Request(unittest.TestCase):
    def test_request_has_prompt_inputs_and_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for d in ("config", ".github"):
                (root / d).symlink_to(ROOT / d)
            (root / ".plans").mkdir()
            ws = "_example"   # in every copy of the repository, before it has workspaces of its own
            plan = {"resource_changes": [change("databricks_sql_endpoint", ["create"], after={"name": "W"})]}
            (root / ".plans" / f"{ws}.json").write_text(json.dumps(plan))
            orig = review.ROOT
            review.ROOT = root
            try:
                (root / ".plans" / f"{ws}.preflight-all.txt").write_text("ok: nothing found that still uses legacy access\n")
                req = review.build_request(review.gather(ws, None))
            finally:
                review.ROOT = orig
        system, user = req["messages"][0]["content"], req["messages"][1]["content"]
        self.assertEqual(system, (ROOT / ".github/ai/plan-review-prompt.md").read_text())
        for tag in ("workspace", "state", "changed_files", "config_diff", "code_diff", "workspace_files", "baseline", "planned_changes", "plan_guard", "preflight"):
            self.assertIn(f"<{tag}>", user)
        self.assertIn("First apply", user)
        self.assertIn("nothing found that still uses legacy access", user, "preflight's findings reach the reviewer")
        self.assertNotIn("#", user.split("<baseline>")[1].split("</baseline>")[0].replace("# config/", ""), "YAML comments are removed")


class CodeDiff(unittest.TestCase):
    """The framework diff explains changes that no config change does (and only Terraform code counts)."""

    def test_terraform_code_and_changelog_but_not_tests_or_docs(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            run = lambda *a: subprocess.run(["git", "-C", tmp, *a], check=True, capture_output=True)
            run("init", "-q"); run("config", "user.email", "t@example.com"); run("config", "user.name", "t")
            files = {"terraform/main.tf": "a\n", "terraform/tests/t.tftest.hcl": "a\n", "CHANGELOG.md": "a\n", "docs/x.md": "a\n"}
            for f, text in files.items():
                (root / f).parent.mkdir(parents=True, exist_ok=True)
                (root / f).write_text(text)
            run("add", "-A"); run("commit", "-q", "-m", "base")
            for f in files:
                (root / f).write_text(f"changed {f}\n")
            orig = review.ROOT
            review.ROOT = root
            try:
                diff = review.code_diff("HEAD")
                listed = review.changed_files("HEAD", "ws")
            finally:
                review.ROOT = orig
        self.assertIn("changed terraform/main.tf", diff)
        self.assertIn("changed CHANGELOG.md", diff)
        self.assertNotIn("tftest", diff)
        self.assertNotIn("docs/x.md", diff)
        self.assertIn("terraform/main.tf: framework code", listed)


class Comments(unittest.TestCase):
    def test_yaml_comments(self):
        text = "# header\n\nsize: Small   # two spaces\nmax: 60 # one space\nurl: \"https://x/#a\"  # quoted\nkey: 'a #b'\n  # indented\n"
        self.assertEqual(review.strip_comments(text), "size: Small\nmax: 60\nurl: \"https://x/#a\"\nkey: 'a #b'")


class Answer(unittest.TestCase):
    def test_text_and_parts(self):
        def resp(content):
            return {"choices": [{"message": {"content": content}}]}
        self.assertEqual(review.response_text(resp("  **Risk** ")), "**Risk**")
        parts = [{"type": "reasoning", "summary": []}, {"type": "text", "text": "answer"}]
        self.assertEqual(review.response_text(resp(parts)), "answer")
        self.assertEqual(review.response_text(resp(json.dumps(parts))), "answer")


if __name__ == "__main__":
    unittest.main()
