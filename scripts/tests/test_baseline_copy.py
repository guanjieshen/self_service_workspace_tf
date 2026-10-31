"""terraform/tests/defaults/ is the baseline as released: the framework repository keeps it the same
as config/defaults/ (an organization changes its own config/defaults/, so this runs only here)."""
import filecmp
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHIPPED, PINNED = ROOT / "config/defaults", ROOT / "terraform/tests/defaults"
# The framework repository's own environment, which a release blanks (scripts/release.py).
ENVIRONMENT = re.compile(r"(?m)^account_id: .*$")


@unittest.skipUnless((ROOT / "dev/README.md").is_file(), "an installed copy: its config/defaults/ is its own")
class BaselineCopy(unittest.TestCase):
    def test_the_pinned_baseline_is_the_shipped_one(self):
        shipped = sorted(p.relative_to(SHIPPED) for p in SHIPPED.rglob("*") if p.is_file() and p.name != ".DS_Store")
        pinned = sorted(p.relative_to(PINNED) for p in PINNED.rglob("*") if p.is_file() and p.name != ".DS_Store")
        self.assertEqual(shipped, pinned, "the same files in config/defaults/ and terraform/tests/defaults/")
        for rel in shipped:
            a, b = SHIPPED / rel, PINNED / rel
            if filecmp.cmp(a, b, shallow=False):
                continue
            with self.subTest(file=str(rel)):
                self.assertEqual(ENVIRONMENT.sub("account_id: null", a.read_text()), ENVIRONMENT.sub("account_id: null", b.read_text()),
                                 f"change terraform/tests/defaults/{rel} with config/defaults/{rel} (AGENTS.md)")


if __name__ == "__main__":
    unittest.main()
