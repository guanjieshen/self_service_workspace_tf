"""scripts/release.py: the zip a customer installs holds none of this repository's environment."""
import io
import pathlib
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout

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

    def test_none_of_this_environment_is_left(self):
        identifiers = rel.own_identifiers(self.files)
        self.assertEqual(rel.leaks(rel.release_files(self.files), identifiers), [])

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

    def test_a_bad_version_is_refused(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            rel.main(["1.0"])


if __name__ == "__main__":
    unittest.main()
