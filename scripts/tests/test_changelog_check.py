"""scripts/changelog_check.py: a pull request that changes framework code says so in CHANGELOG.md."""
import unittest

from helpers import ROOT, load

check = load("changelog_check")


class ChangelogCheck(unittest.TestCase):
    def test_framework_code_without_a_changelog_entry_fails_and_says_what_to_add(self):
        ok, message = check.report(["apps/self-service/portal.py", "apps/self-service/tests/test_portal.py"])
        self.assertFalse(ok)
        self.assertIn("apps/self-service/portal.py", message)
        self.assertNotIn("tests/test_portal.py", message.split("Add an entry")[0], "tests are not framework code")
        self.assertIn('"## Unreleased"', message)
        self.assertIn("agents/app.md", message, "the guide to keep true")

    def test_with_its_entry_it_passes_and_still_names_the_guides(self):
        ok, message = check.report(["apps/self-service/db/migrations/009_x.sql", "CHANGELOG.md"])
        self.assertTrue(ok)
        self.assertIn("agents/database.md", message)

    def test_a_guide_changed_too_is_not_named_again(self):
        ok, message = check.report(["terraform/main.tf", "CHANGELOG.md", "agents/terraform.md"])
        self.assertTrue(ok)
        self.assertNotIn("agents/terraform.md", message)

    def test_docs_tests_and_an_organizations_own_files_need_no_entry(self):
        for changed in (["README.md", "docs/SETUP.md", "agents/app.md"], ["terraform/tests/baseline.tftest.hcl"],
                        ["config/workspaces/hr.yaml", ".github/CODEOWNERS"], []):
            with self.subTest(changed=changed):
                self.assertTrue(check.report(changed)[0])

    def test_every_framework_folder_counts(self):
        for path in ("bundle/jobs/resources/jobs.yml", "scripts/tf.sh", "terraform/main.tf", "install/copy_to_your_repo.py",
                     ".github/workflows/deploy.yml"):
            with self.subTest(path=path):
                self.assertFalse(check.report([path])[0])

    def test_each_guide_it_names_exists(self):
        for _, guide in check.GUIDES:
            with self.subTest(guide=guide):
                self.assertTrue((ROOT / guide).exists())


if __name__ == "__main__":
    unittest.main()
