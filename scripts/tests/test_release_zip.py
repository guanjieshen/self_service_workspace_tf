"""scripts/release.py: the zip a customer installs holds none of this repository's environment."""
import io
import os
import pathlib
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from helpers import load

rel = load("release")


class ReleaseZip(unittest.TestCase):
    def setUp(self):
        self.files = rel.committed_files()

    def test_leaves_out_this_environment(self):
        out = rel.release_files(self.files)
        self.assertFalse([p for p in out if p.startswith("dev/")], "dev/ is the framework's own")
        self.assertNotIn("config/backend.hcl", out)
        self.assertEqual(sorted(p for p in out if p.startswith("config/workspaces/")), ["config/workspaces/_example.yaml"])

    def test_leaves_out_a_workspace_folder(self):
        out = rel.release_files({**self.files, "config/workspaces/x/genie-code/skills/y/SKILL.md": b"x"})
        self.assertEqual(sorted(p for p in out if p.startswith("config/workspaces/")), ["config/workspaces/_example.yaml"])

    def test_blanks_the_values_and_keeps_the_instructions(self):
        out = rel.release_files(self.files)
        setup = out["config/setup.yaml"].decode()
        for key in ("tenant_id", "subscription_id", "state_storage_account", "ai_review_host", "ai_review_model", "pipeline_client_id"):
            with self.subTest(key=key):
                self.assertRegex(setup, rf"(?m)^{key}: null\b")
        self.assertIn("# ---- REQUIRED", setup, "the comments stay: they are the instructions")
        self.assertRegex(out["config/defaults/cost.yaml"].decode(), r"(?m)^account_id: null\b")
        owners = out[".github/CODEOWNERS"].decode()
        self.assertRegex(owners, r"(?m)^\*\s+@your-org/databricks-platform$")
        self.assertRegex(owners, r"(?m)^/config/defaults/settings\.yaml\s+@your-org/databricks-platform @your-org/security$",
                         "the security settings keep a separate security reviewer")

    def test_the_self_service_hub_is_a_template(self):
        """config/self-service/hub.yaml: no hub, database or app identities of this repository's."""
        hub = rel.release_files(self.files)["config/self-service/hub.yaml"].decode()
        for key in ("name", "host", "warehouse_id", "self_service", "approvals"):
            with self.subTest(key=key):
                self.assertNotRegex(hub, rf"(?m)^  {key}: (?!null\b)\S")
        self.assertRegex(hub, r"(?m)^  readers: \[\]")
        self.assertRegex(hub, r"(?m)^adopt: \{\}$")
        self.assertIn("users_group: users", hub, "the groups' defaults stay")

    def test_none_of_this_environment_is_left(self):
        identifiers = rel.own_identifiers(self.files)
        self.assertEqual(rel.leaks(rel.release_files(self.files), identifiers), [])

    def test_a_workspace_file_started_from_the_example_is_not_a_leak(self):
        """An organization's workspace files begin as copies of _example.yaml: its commented lines and
        <placeholders> are nobody's environment, so _example.yaml itself never counts as a leak."""
        files = dict(self.files)
        example = files["config/workspaces/_example.yaml"].decode()
        files["config/workspaces/hr.yaml"] = (example + "\n# storage_root: abfss://data@realaccount.dfs.core.windows.net/hr\n").encode()
        identifiers = rel.own_identifiers(files)
        self.assertFalse([i for i in identifiers if "<" in i], "no placeholder is an identifier")
        self.assertNotIn("abfss://data@realaccount.dfs.core.windows.net/hr", identifiers, "a commented line is not a value")
        files["config/workspaces/hr.yaml"] = (example.replace("host: https://adb-0000000000000000.0.azuredatabricks.net",
                                                              "host: https://adb-1234500000000001.1.azuredatabricks.net")
                                              + "\nstorage_root: abfss://data@realaccount.dfs.core.windows.net/hr\n").encode()
        identifiers = rel.own_identifiers(files)
        self.assertIn("abfss://data@realaccount.dfs.core.windows.net/hr", identifiers, "its real values still are")
        self.assertIn("https://adb-1234500000000001.1.azuredatabricks.net", identifiers)

    def test_a_leak_stops_the_build(self):
        files = dict(self.files)
        files["config/setup.yaml"] = b"tenant_id: 11111111-2222-3333-4444-555555555555\n"
        files["docs/x.md"] = b"see tenant 11111111-2222-3333-4444-555555555555\n"
        self.assertIn(("docs/x.md", "11111111-2222-3333-4444-555555555555"),
                      rel.leaks(rel.release_files(files), rel.own_identifiers(files)))

    def test_builds_a_zip_with_one_top_folder(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(rel.main(["v9.9.9", "--out", tmp]), 0)
            [zip_path] = pathlib.Path(tmp).glob("*.zip")
            with zipfile.ZipFile(zip_path) as z:
                names = z.namelist()
        self.assertTrue(all(n.startswith(zip_path.stem + "/") for n in names))
        self.assertIn(f"{zip_path.stem}/README.md", names)
        self.assertIn(f"{zip_path.stem}/VERSION", names, "an installation can tell which release it runs")

    def test_the_release_branch_holds_the_release_with_script_modes(self):
        # In a throwaway repository: the branch must not touch this one's refs.
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(rel, "ROOT", pathlib.Path(tmp)):
            git = lambda *a: subprocess.run(["git", "-C", tmp, *a], capture_output=True, text=True, check=True).stdout
            git("init", "--quiet")
            git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "--allow-empty", "--quiet", "-m", "start")
            files = {"README.md": b"hello\n", "scripts/tf.sh": b"#!/usr/bin/env bash\n", "VERSION": b"v9.9.9\n"}
            with mock.patch.dict(os.environ, {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                                              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}):
                branch, first = rel.write_branch(files, "v9.9.9")
                _, second = rel.write_branch(files, "v9.9.9")
            self.assertEqual(branch, "release/v9.9.9")
            tree = git("ls-tree", "-r", branch)
            self.assertRegex(tree, r"(?m)^100755 blob \w+\tscripts/tf\.sh$", "scripts stay executable")
            self.assertRegex(tree, r"(?m)^100644 blob \w+\tREADME\.md$")
            self.assertEqual(git("show", f"{branch}:VERSION"), "v9.9.9\n")
            self.assertEqual(git("rev-parse", f"{second}^").strip(), first, "a rebuild goes on top of the branch")
            self.assertEqual(git("status", "--porcelain"), "", "the working tree is untouched")

    def test_a_bad_version_is_refused(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            rel.main(["1.0"])


if __name__ == "__main__":
    unittest.main()
