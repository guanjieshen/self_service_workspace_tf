"""Terraform patterns that mocked plans cannot catch, checked in the source.

Both were found on a real plan: adding one group assignment planned every persona
group's entitlements and the Personal Compute permissions as replaced (false risky
changes that block the pull request).
"""
import re
import unittest

from helpers import ROOT

TF = ROOT / "terraform"


class Structure(unittest.TestCase):
    def test_no_module_depends_on_another_module(self):
        # A module-level depends_on on a module defers every data source in the dependent
        # module until apply whenever the other module has changes. Pass a value from the
        # other module instead (as module.personas.group_names is used in main.tf).
        main = (TF / "main.tf").read_text()
        self.assertEqual(re.findall(r"depends_on\s*=\s*\[[^\]]*module\.", main), [])

    def test_entitlements_ignore_an_unknown_group_id(self):
        src = (TF / "modules/personas/main.tf").read_text()
        block = re.search(r'resource "databricks_entitlements" "persona" \{.*?\n\}', src, re.S).group(0)
        self.assertRegex(block, r"ignore_changes\s*=\s*\[group_id\]")


if __name__ == "__main__":
    unittest.main()
