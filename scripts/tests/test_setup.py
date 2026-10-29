"""scripts/setup.py: each step's script is valid bash, safe to run again, and matches the workflows."""
import contextlib
import io
import pathlib
import re
import subprocess
import tempfile
import unittest
from unittest import mock

from helpers import ROOT, load

setup = load("setup")

STEPS = {
    "state": ["--tenant-id", "tenant", "--subscription", "sub", "--resource-group", "rg-tf", "--location", "canadacentral",
              "--storage-account", "sttf", "--container", "tfstate"],
    "identity": ["--tenant-id", "tenant", "--subscription", "sub", "--resource-group", "rg-tf", "--storage-account", "sttf",
                 "--container", "tfstate", "--repo", "org/repo"],
    "github": ["--repo", "org/repo", "--client-id", "app", "--tenant-id", "tenant", "--subscription", "sub"],
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
        for step in ("state", "identity"):
            lines = render(step).splitlines()
            for n, line in enumerate(lines):
                if re.search(r"(az [\w -]+|service-principals) create\b", line):
                    with self.subTest(step=step, line=line):
                        self.assertTrue("||" in line + lines[n - 1] or lines[n - 1].strip() == "else", line)

    def test_an_existing_storage_account_is_left_as_it_is(self):
        script = render("state")
        exists, create = script.index("then\n  # Someone else's account"), script.index("az storage account create")
        versioning = script.index("--enable-versioning true")
        self.assertLess(exists, create)
        self.assertLess(create, versioning, "versioning and soft delete only on an account this step created")
        self.assertLess(versioning, script.index("\nfi\n"))

    def test_the_azure_steps_stop_in_the_wrong_tenant(self):
        for step in ("state", "identity"):
            script = render(step)
            with self.subTest(step=step):
                check = script.index('[ "$(az account show --query tenantId -o tsv)" = tenant ] ||')
                first_create = min(script.index(c) for c in ("az group create", "az ad app create") if c in script)
                self.assertLess(check, first_create, "the tenant is checked before anything is created")

    def test_the_repository_defaults_to_the_origin_and_is_shown(self):
        args = ["github", "--client-id", "c", "--tenant-id", "t", "--subscription", "s"]
        with mock.patch.object(setup, "origin_repo", lambda: "acme/baseline"), \
                mock.patch.object(setup.wsf, "top_level", lambda path: {}):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                setup.main(args)
            self.assertIn('echo "Repository: acme/baseline (from this clone\'s git origin)."', out.getvalue())
            self.assertIn("gh variable set AZURE_CLIENT_ID -R acme/baseline", out.getvalue())
            with contextlib.redirect_stdout(io.StringIO()) as out:
                setup.main([*args, "--repo", "acme/other"])
            self.assertIn("Repository: acme/other (from config/setup.yaml)", out.getvalue(), "a set value wins")
        with mock.patch.object(setup, "origin_repo", lambda: None), \
                mock.patch.object(setup.wsf, "top_level", lambda path: {}), self.assertRaises(SystemExit) as e:
            setup.main(args)
        self.assertIn("no GitHub origin: fill in github_repo", str(e.exception))
        for url, repo in (("git@github.com:acme/baseline.git", "acme/baseline"), ("https://github.com/acme/base.line", "acme/base.line"),
                          ("https://gitlab.com/acme/x.git", None)):
            with mock.patch.object(setup.subprocess, "run", lambda *a, **k: mock.Mock(stdout=url)):
                self.assertEqual(setup.origin_repo(), repo)

    def test_identity_says_which_repository_it_will_trust(self):
        self.assertIn('echo "Repository: org/repo (from config/setup.yaml). Entra will trust only its pull requests and main branch."',
                      render("identity"))

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
        names = re.findall(r"^    name: (.+)$", (ROOT / ".github/workflows/checks.yml").read_text(), re.M)
        for check in setup.REQUIRED_CHECKS:
            self.assertIn(check, names)
        self.assertIn('"contexts": ["Format and validate", "Tests"]', render("github"))

    def test_approvers_become_required_reviewers(self):
        script = render("github")
        self.assertNotIn('"reviewers"', script)
        self.assertIn("environments/apply-approval >/dev/null 2>&1 ||\n  gh api -X PUT", script,
                      "without apply_approvers, reviewers added in the UI are kept: create the environment only if missing")
        script = render("github", "--approvers", "org/platform")
        self.assertIn("TEAM_ID=$(gh api orgs/org/teams/platform --jq .id)", script)
        self.assertIn('"reviewers": [{"type": "Team", "id": $TEAM_ID}]', script)

    def test_bad_names_are_refused(self):
        for args in (["github", "--repo", "org/repo;rm", "--client-id", "a", "--tenant-id", "t", "--subscription", "s"],
                     ["github", "--repo", "org/repo", "--client-id", "a", "--tenant-id", "t", "--subscription", "s", "--approvers", "x"]):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                setup.main(args)


class SetupFile(unittest.TestCase):
    """Every value comes from config/setup.yaml; a flag overrides one."""

    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "setup.yaml"
        # The repository's own file, with every value emptied (it may be filled in here).
        blank = re.sub(r"(?m)^(\w+:)[ \t]*[^\s#]+", r"\1 null", (ROOT / "config/setup.yaml").read_text())
        self.path.write_text(blank)
        patcher = mock.patch.object(setup, "setup_file", lambda: self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fill(self, key, value):
        self.assertTrue(setup.remember(self.path, key, value))

    STATE = (("tenant_id", "ten-1"), ("subscription_id", "sub-1"), ("state_location", "canadacentral"),
             ("state_resource_group", "rg-1"), ("state_storage_account", "stfile"), ("state_container", "tfstate"))

    def test_missing_values_are_named(self):
        with self.assertRaises(SystemExit) as e:
            setup.main(["state"])
        self.assertIn("Fill in tenant_id, subscription_id, state_location, state_resource_group, state_storage_account, "
                      "state_container in", str(e.exception))

    def test_values_come_from_the_file(self):
        for key, value in self.STATE:
            self.fill(key, value)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            setup.main(["state"])
        self.assertIn('storage_account_name = "stfile"', out.getvalue())
        self.assertIn("az account set --subscription sub-1", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as out2:
            setup.main(["state", "--storage-account", "stflag"])
        self.assertIn('storage_account_name = "stflag"', out2.getvalue(), "a flag overrides the file")

    def test_required_values_are_at_the_top_and_the_rest_have_defaults(self):
        text = (ROOT / "config/setup.yaml").read_text()
        required = text[text.index("# ---- REQUIRED"):text.index("# ---- OPTIONAL")]
        self.assertEqual(re.findall(r"(?m)^(\w+):", required),
                         ["tenant_id", "subscription_id", "state_location", "state_resource_group", "state_storage_account",
                          "state_container"])
        # Required means no default: a required value is asked for, never guessed.
        for _, key, default, steps in setup.OPTIONS:
            if key in re.findall(r"(?m)^(\w+):", required):
                self.assertTrue(steps and default is None, key)
        keys = re.findall(r"(?m)^(\w+):", text)
        # The ai_review_* values are read by scripts/ai-plan-review.py, every other one by setup.py.
        self.assertEqual(sorted(keys), sorted([k for _, k, _, _ in setup.OPTIONS] + ["ai_review_model", "ai_review_workspace"]),
                         "every value in the file is read, and only those")

    def test_ids_from_identity_are_asked_for_by_name(self):
        for key, value in (("tenant_id", "ten-1"), ("subscription_id", "sub-1")):
            self.fill(key, value)
        with self.assertRaises(SystemExit) as e:
            setup.main(["github"])
        self.assertIn("pipeline_client_id not set yet", str(e.exception))
        self.assertIn("setup.py identity --run", str(e.exception))

    def test_remember_fills_only_a_null_value_and_keeps_comments(self):
        self.fill("pipeline_client_id", "app-1")
        self.assertFalse(setup.remember(self.path, "pipeline_client_id", "app-2"), "never overwrites a value")
        self.assertRegex(self.path.read_text(), r"(?m)^pipeline_client_id: app-1 +# the service principal")

    def test_identity_ids_are_saved_when_it_runs(self):
        script = 'echo "  client ID (AZURE_CLIENT_ID): app-9"'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.run(script, self.path), 0)
        self.assertIn("pipeline_client_id: app-9", self.path.read_text())


if __name__ == "__main__":
    unittest.main()
