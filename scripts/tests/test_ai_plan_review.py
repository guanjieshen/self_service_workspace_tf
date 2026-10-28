"""scripts/ai-plan-review.py: settings, what the reviewer is shown, and reading the answer."""
import base64
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest

from helpers import ROOT, SCRIPTS, change, load

review = load("ai-plan-review")


class Settings(unittest.TestCase):
    def write(self, text):
        f = pathlib.Path(tempfile.mkdtemp()) / "ai-review.yaml"
        f.write_text(text)
        return f

    def test_repository_settings_are_valid(self):
        s = review.load_settings()
        self.assertIsInstance(s["enabled"], bool)
        self.assertIsInstance(s["max_tokens"], int)
        self.assertTrue((ROOT / s["prompt"]).exists(), "the prompt file in config/ai-review.yaml exists")

    def test_types_and_comments(self):
        orig = review.SETTINGS
        try:
            review.SETTINGS = self.write("enabled: true   # on\nmax_tokens: 123\nendpoint: \"system.ai.x\"\n# endpoint: other\n")
            s = review.load_settings()
        finally:
            review.SETTINGS = orig
        self.assertEqual((s["enabled"], s["max_tokens"], s["endpoint"]), (True, 123, "system.ai.x"))

    def test_unknown_setting_fails(self):
        orig = review.SETTINGS
        try:
            review.SETTINGS = self.write("colour: blue\n")
            with self.assertRaises(ValueError):
                review.load_settings()
        finally:
            review.SETTINGS = orig


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
                req = review.build_request(ws, None, review.load_settings())
            finally:
                review.ROOT = orig
        system, user = req["messages"][0]["content"], req["messages"][1]["content"]
        self.assertEqual(system, (ROOT / ".github/ai/plan-review-prompt.md").read_text())
        for tag in ("workspace", "state", "changed_files", "config_diff", "workspace_files", "baseline", "planned_changes", "plan_guard"):
            self.assertIn(f"<{tag}>", user)
        self.assertIn("First apply", user)
        self.assertNotIn("#", user.split("<baseline>")[1].split("</baseline>")[0].replace("# config/", ""), "YAML comments are removed")


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



class WorkspaceSettings(unittest.TestCase):
    """A workspace's ai-review.yaml overrides the repository settings, but never the prompts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = (review.ROOT, review.SETTINGS)
        repo = pathlib.Path(self.tmp.name)
        ws_dir = repo / "config/workspaces/wsx"
        ws_dir.mkdir(parents=True)
        repo_settings = repo / "settings.yml"
        review.ROOT, review.SETTINGS = repo, repo_settings
        self.ws_dir = ws_dir
        self.repo_settings = repo_settings

    def tearDown(self):
        review.ROOT, review.SETTINGS = self.orig
        self.tmp.cleanup()

    def test_workspace_overrides_the_limits(self):
        self.repo_settings.write_text("enabled: true\nendpoint: system.ai.x\nmax_tokens: 4000\n")
        (self.ws_dir / "ai-review.yaml").write_text("max_tokens: 1200\n")
        s = review.load_settings("wsx")
        self.assertEqual(s["max_tokens"], 1200)
        self.assertEqual(s["endpoint"], "system.ai.x", "keys the workspace does not set stay shared")

    def test_model_override_sets_its_label(self):
        self.repo_settings.write_text("enabled: true\nendpoint: system.ai.x\n")
        (self.ws_dir / "ai-review.yaml").write_text("endpoint: system.ai.haiku\nmax_tokens: 2000\n")
        s = review.load_settings("wsx")
        self.assertEqual((s["label"], s["endpoint"], s["max_tokens"]), ("system.ai.haiku", "system.ai.haiku", 2000))

    def test_without_a_file_the_repository_settings_hold(self):
        self.repo_settings.write_text("enabled: true\nendpoint: system.ai.x\n")
        s = review.load_settings("wsx")
        self.assertEqual(s["endpoint"], "system.ai.x")

    def test_dev_workspace_folder(self):
        dev = pathlib.Path(self.tmp.name) / "dev/workspaces/devws"
        dev.mkdir(parents=True)
        (dev / "workspace.yaml").write_text("host: https://h\n")
        (dev / "ai-review.yaml").write_text("endpoint: system.ai.dev\n")
        self.repo_settings.write_text("enabled: true\n")
        self.assertEqual(review.load_settings("devws")["endpoint"], "system.ai.dev")
        self.assertEqual(review.workspace_field("devws", "host"), "https://h")

    def test_unknown_key_and_shared_prompts_refused(self):
        self.repo_settings.write_text("enabled: true\n")
        (self.ws_dir / "ai-review.yaml").write_text("engine: genie-code\n")
        with self.assertRaises(ValueError):
            review.load_settings("wsx")
        (self.ws_dir / "ai-review.yaml").write_text("prompt: my-prompt.md\n")
        with self.assertRaises(ValueError):
            review.load_settings("wsx")



if __name__ == "__main__":
    unittest.main()
