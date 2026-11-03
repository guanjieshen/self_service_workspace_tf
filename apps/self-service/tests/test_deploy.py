"""scripts/app_deploy.py: the order and the rules of a deploy, with a stand-in for the CLI."""
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import app_deploy  # noqa: E402


class ProjectExists(unittest.TestCase):
    def test_a_deleted_project_stops_the_deploy_saying_how_to_clear_it(self):
        deleted = {"name": "projects/cd-self-service", "delete_time": "2026-11-02T23:32:47Z", "purge_time": "2026-11-09T23:32:47Z"}
        with mock.patch.object(app_deploy, "cli", return_value=deleted), self.assertRaises(SystemExit) as e:
            app_deploy.project_exists("https://h", "cd-self-service")
        self.assertIn("undelete-project", str(e.exception))
        self.assertIn("--purge", str(e.exception))

    def test_only_a_real_not_found_counts_as_missing(self):
        done = lambda code, err="": mock.Mock(returncode=code, stdout="", stderr=err)
        with mock.patch.object(app_deploy.subprocess, "run", return_value=done(1, "Error: project projects/p does not exist")):
            self.assertIsNone(app_deploy.cli("https://h", "postgres", "get-project", "projects/p", missing_ok=True))
        for err in ("Error: cannot get access token: login.html", "dial tcp: i/o timeout", "PERMISSION_DENIED"):
            with self.subTest(err=err), mock.patch.object(app_deploy.subprocess, "run", return_value=done(1, err)), \
                    self.assertRaises(SystemExit, msg="an outage is never read as 'not there'"):
                app_deploy.cli("https://h", "postgres", "get-project", "projects/p", missing_ok=True)
        with mock.patch.object(app_deploy.subprocess, "run", return_value=done(1, "not found")), self.assertRaises(SystemExit):
            app_deploy.cli("https://h", "postgres", "get-project", "projects/p")   # without missing_ok, any failure stops

    def test_missing_and_present(self):
        with mock.patch.object(app_deploy, "cli", return_value=None):
            self.assertFalse(app_deploy.project_exists("https://h", "p"))
        with mock.patch.object(app_deploy, "cli", return_value={"name": "projects/p"}):
            self.assertTrue(app_deploy.project_exists("https://h", "p"))


class JobsGrantOnlyTheAssignedApps(unittest.TestCase):
    """A job cannot grant a service principal its workspace does not have: only hub.yaml's app_ids
    (the ones Terraform assigned) are granted, never the apps the hub deploy just created."""

    def run_main(self, app_ids):
        s = {"spokes": ["spoke"], "app_ids": app_ids}
        granted = []
        with mock.patch.object(app_deploy.app_build, "load", return_value=s), \
             mock.patch.object(app_deploy.app_build, "served", return_value=[{"name": "spoke"}]), \
             mock.patch.object(app_deploy, "outputs", return_value={}), \
             mock.patch.object(app_deploy, "deploy_hub", return_value=["new-1", "new-2"]), \
             mock.patch.object(app_deploy, "deploy_jobs", side_effect=lambda s, w, ids, plan: granted.append(ids)):
            app_deploy.main([])
        return granted

    def test_a_first_install_grants_none(self):
        self.assertEqual(self.run_main({"self_service": None, "approvals": None}), [[]])

    def test_then_the_ids_in_hub_yaml(self):
        self.assertEqual(self.run_main({"self_service": "a", "approvals": "b"}), [["a", "b"]])


if __name__ == "__main__":
    unittest.main()
