"""The GitHub Actions workflows stay hardened: what a reviewer would otherwise have to remember.

Parsed with plain text rules (standard library only), on the files' own layout: two-space
indentation, one job per "  <name>:" line under "jobs:".
"""
import re
import unittest

from helpers import ROOT

WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml"))
ACTIONS = sorted((ROOT / ".github/actions").glob("*/action.yml"))


def jobs(path):
    """job name => its text, for one workflow file."""
    lines = path.read_text().splitlines()
    out, name = {}, None
    for line in lines[lines.index("jobs:") + 1:]:
        m = re.match(r"^  ([\w-]+):\s*$", line)
        if m:
            name = m.group(1)
            out[name] = []
        elif name and (line.startswith("    ") or not line.strip()):
            out[name].append(line)
        elif line and not line.startswith(" "):
            break
    return {k: "\n".join(v) for k, v in out.items()}


class Workflows(unittest.TestCase):
    def test_third_party_actions_are_pinned_to_a_commit(self):
        # A tag can be moved to other code; a commit SHA cannot. Dependabot proposes updates.
        for path in WORKFLOWS + ACTIONS:
            for n, line in enumerate(path.read_text().splitlines(), 1):
                m = re.search(r"uses:\s*([^\s#]+)", line)
                if m and not m.group(1).startswith("./"):
                    with self.subTest(file=path.name, line=n):
                        self.assertRegex(m.group(1), r"@[0-9a-f]{40}$", f"{path.name}:{n}: pin {m.group(1)} to a commit SHA")
                        self.assertRegex(line, r"#\s*v\d", f"{path.name}:{n}: name the version in a comment")

    def test_every_job_has_its_own_permissions_and_a_time_limit(self):
        for path in WORKFLOWS:
            grants_nothing = re.search(r"(?m)^permissions: \{\}", path.read_text())
            for name, block in jobs(path).items():
                with self.subTest(workflow=path.name, job=name):
                    self.assertRegex(block, r"(?m)^    timeout-minutes: \d+", "a hung runner must not hold a workspace for hours")
                    if grants_nothing:
                        self.assertRegex(block, r"(?m)^    permissions:", "the workflow grants nothing: each job asks")

    def test_only_jobs_that_sign_in_get_an_oidc_token(self):
        for name, block in jobs(ROOT / ".github/workflows/deploy.yml").items():
            signs_in = ("./.github/actions/setup" in block and 'sign-in: "false"' not in block) or "azure/login" in block
            with self.subTest(job=name):
                self.assertEqual("id-token: write" in block, signs_in, f"{name}: id-token only where it signs in")

    def test_checkout_keeps_no_token_unless_git_needs_it(self):
        # Only the apply job talks to the remote afterwards (git ls-remote, on a re-run).
        for path in WORKFLOWS:
            for name, block in jobs(path).items():
                if "actions/checkout@" not in block:
                    continue
                with self.subTest(workflow=path.name, job=name):
                    if "ls-remote" in block:
                        self.assertNotIn("persist-credentials: false", block)
                    else:
                        self.assertIn("persist-credentials: false", block)

    def test_plans_never_take_the_state_lock(self):
        # A plan does not write the state; locking it only collides with applies.
        for line in (ROOT / ".github/workflows/deploy.yml").read_text().splitlines():
            if "tf.sh" in line and " plan " in line:
                self.assertIn("-lock=false", line)
            if "tf.sh" in line and " apply " in line:
                self.assertNotIn("-lock=false", line)


    def test_the_approval_label_re_runs_the_check(self):
        # Without labeled/unlabeled, adding allow-risky-changes leaves the check red until a push.
        deploy = (ROOT / ".github/workflows/deploy.yml").read_text()
        self.assertRegex(deploy, r"(?m)^    types: \[[^\]]*\blabeled\b[^\]]*\bunlabeled\b")
        self.assertIn("github.event.label.name == 'allow-risky-changes'", jobs(ROOT / ".github/workflows/deploy.yml")["route"],
                      "other labels do not re-run the plans")


    def test_a_flagged_apply_needs_the_label_on_the_merged_pull_request(self):
        # The approval is checked at apply time: a pull request can be merged with a failed plan.
        apply = jobs(ROOT / ".github/workflows/deploy.yml")["apply"]
        self.assertIn("allow-risky-changes", apply)
        self.assertIn("listPullRequestsAssociatedWithCommit", apply)
        self.assertRegex(apply, r"CONFIRM_ENV: \$\{\{ steps\.approval\.outputs\.approved == 'true' && matrix\.workspace \|\| '' \}\}")
        self.assertNotRegex(apply, r"(?m)^      CONFIRM_ENV:", "never set for the whole job")


if __name__ == "__main__":
    unittest.main()
