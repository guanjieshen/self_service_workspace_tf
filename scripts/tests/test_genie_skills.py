"""The baseline's Genie Code skills (config/defaults/genie-code/skills/): each is a folder named in
lowercase letters, digits and hyphens, with a SKILL.md whose front matter gives that name and a
description. Genie Code reads the description to decide when to use a skill, and ignores one
it cannot read. Checks the organization's baseline and the copy the Terraform tests use."""
import re
import unittest

from helpers import ROOT

BASELINES = [ROOT / "config/defaults/genie-code/skills", ROOT / "terraform/tests/defaults/genie-code/skills"]


def front_matter(text):
    """name and description from the --- block that follows any leading <!-- comment -->."""
    text = re.sub(r"(?s)^\s*<!--.*?-->\s*", "", text)
    m = re.match(r"(?s)^---\r?\n(.*?)\r?\n---", text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            out[key.strip()] = value.strip()
    return out


class Skills(unittest.TestCase):
    def test_every_skill_is_well_formed(self):
        for base in BASELINES:
            for folder in sorted(p for p in base.iterdir() if p.is_dir()):
                with self.subTest(skill=str(folder.relative_to(ROOT))):
                    self.assertRegex(folder.name, r"^[a-z0-9]+(-[a-z0-9]+)*$", "folder: lowercase letters, digits, hyphens")
                    skill = folder / "SKILL.md"
                    self.assertTrue(skill.exists(), "every skill folder has a SKILL.md")
                    meta = front_matter(skill.read_text())
                    self.assertEqual(meta.get("name"), folder.name, "the front matter's name is the folder's")
                    self.assertTrue(meta.get("description"), "the front matter gives a description")

    def test_the_check_reads_front_matter_after_a_comment(self):
        self.assertEqual(front_matter("<!-- note -->\n---\nname: a\ndescription: b\n---\nbody"), {"name": "a", "description": "b"})
        self.assertEqual(front_matter("no front matter"), {})


if __name__ == "__main__":
    unittest.main()
