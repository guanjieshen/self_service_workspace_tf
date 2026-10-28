"""scripts/setup.py: each step's script is valid bash, safe to run again, and matches the workflows."""
import contextlib
import io
import re
import subprocess
import unittest

from helpers import ROOT, load

setup = load("setup")

STEPS = {
    "state": ["--subscription", "sub", "--resource-group", "rg-tf", "--location", "canadacentral", "--storage-account", "sttf"],
    "identity": ["--subscription", "sub", "--resource-group", "rg-tf", "--storage-account", "sttf", "--repo", "org/repo"],
    "github": ["--repo", "org/repo", "--client-id", "app", "--tenant-id", "tenant", "--subscription", "sub"],
    "databricks": ["--client-id", "app", "--account-profile", "acct"],
}


def render(step, *extra):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        setup.main([step, *STEPS[step], *extra])
    return out.getvalue()


class Scripts(unittest.TestCase):
    def test_every_step_is_valid_bash(self):
        for step in STEPS:
            with self.subTest(step=step):
                r = subprocess.run(["bash", "-n"], input=render(step), text=True, capture_output=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_printing_runs_nothing(self):
        def refuse(*a, **k):
            raise AssertionError("printed a step but ran something")
        original, setup.subprocess.run = setup.subprocess.run, refuse
        try:
            for step in STEPS:
                render(step)
        finally:
            setup.subprocess.run = original

    def test_every_create_is_checked_first(self):
        # Safe to run again: each create is the right side of "<exists> || <create>".
        for step in ("state", "identity", "databricks"):
            lines = render(step).splitlines()
            for n, line in enumerate(lines):
                if re.search(r"(az [\w -]+|service-principals) create\b", line):
                    with self.subTest(step=step, line=line):
                        self.assertIn("||", line + lines[n - 1])

    def test_state_is_private(self):
        script = render("state")
        for flag in ("--allow-blob-public-access false", "--allow-shared-key-access false", "--public-access off",
                     "--enable-versioning true", 'storage_account_name = "sttf"', "use_azuread_auth     = true"):
            self.assertIn(flag, script)

    def test_federated_credentials_match_how_the_workflows_sign_in(self):
        script = render("identity")
        self.assertIn("gh api repos/org/repo/actions/oidc/customization/sub --jq .sub_claim_prefix", script)
        self.assertIn('"subject": "\'"$PREFIX"\':pull_request"', script)          # Plan
        self.assertIn('"subject": "\'"$PREFIX"\':ref:refs/heads/main"', script)   # Apply and Drift
        self.assertIn('--role "Storage Blob Data Contributor" --scope "$SCOPE"', script)
        workflows = "".join(p.read_text() for p in (ROOT / ".github/workflows").glob("*.yml"))
        # A job that signs in in an environment would sign in as environment:<name> instead.
        self.assertEqual(re.findall(r"environment: (.+)", workflows), ["apply-approval"])

    def test_required_checks_are_jobs_of_the_plan_workflow(self):
        names = re.findall(r"^    name: (.+)$", (ROOT / ".github/workflows/plan.yml").read_text(), re.M)
        for check in setup.REQUIRED_CHECKS:
            self.assertIn(check, names)
        self.assertIn('"contexts": ["Format and validate", "Tests"]', render("github"))

    def test_approvers_become_required_reviewers(self):
        script = render("github")
        self.assertNotIn('"reviewers"', script)
        self.assertIn("environments/apply-approval >/dev/null 2>&1 ||\n  gh api -X PUT", script,
                      "without --approvers, reviewers added in the UI are kept: create the environment only if missing")
        script = render("github", "--approvers", "org/platform")
        self.assertIn("TEAM_ID=$(gh api orgs/org/teams/platform --jq .id)", script)
        self.assertIn('"reviewers": [{"type": "Team", "id": $TEAM_ID}]', script)

    def test_databricks_makes_the_sp_admin_of_each_workspace(self):
        load_ws = setup.wsf
        original = load_ws.WORKSPACES
        try:
            load_ws.WORKSPACES = ROOT / "terraform/tests/fixtures"
            script = render("databricks", "full")
        finally:
            load_ws.WORKSPACES = original
        self.assertIn("workspace-assignment update -p acct 1111111111111111 \"$DBX_SP\" --json '{\"permissions\": [\"ADMIN\"]}'", script)

    def test_bad_names_are_refused(self):
        for args in (["github", "--repo", "org/repo;rm", "--client-id", "a", "--tenant-id", "t", "--subscription", "s"],
                     ["github", "--repo", "org/repo", "--client-id", "a", "--tenant-id", "t", "--subscription", "s", "--approvers", "x"]):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                setup.main(args)


if __name__ == "__main__":
    unittest.main()
