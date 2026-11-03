"""agents/skills/: the Genie Code skills that guide an organization's admins (docs/SETUP.md, step 2).

Each is a folder with a SKILL.md in the Agent Skills format: front matter with its name (the
folder's) and a description Genie Code matches requests against. A skill that hands over to
another names it, so that one must exist. Paths in them are checked by test_docs.py.
"""
import re
import unittest

from helpers import ROOT

SKILLS = ROOT / "agents/skills"


def front_matter(path):
    """{key: value} from the --- block at the top of a SKILL.md, or {} if it has none."""
    m = re.match(r"---\n(.*?)\n---\n", path.read_text(), re.S)
    return dict(re.findall(r"(?m)^([a-z_]+):\s*(.+)$", m.group(1))) if m else {}


class Skills(unittest.TestCase):
    def test_the_admins_tasks_each_have_a_skill(self):
        names = {p.name for p in SKILLS.iterdir() if p.is_dir()}
        self.assertLessEqual({"pull-request-from-databricks", "add-workspace", "change-all-workspaces",
                              "change-one-workspace", "update-self-service-app"}, names)

    def test_each_is_a_folder_with_a_well_formed_skill(self):
        for folder in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
            with self.subTest(skill=folder.name):
                meta = front_matter(folder / "SKILL.md")
                self.assertEqual(meta.get("name"), folder.name, "the front matter's name is the folder's")
                self.assertRegex(folder.name, r"^[a-z0-9]+(-[a-z0-9]+)*$", "lowercase words and dashes")
                description = meta.get("description", "")
                self.assertTrue(description.startswith("Use when"), "say when to use it: Genie Code matches on it")
                self.assertLessEqual(len(description), 1024, "the Agent Skills limit")

    def test_a_skill_it_hands_over_to_exists(self):
        names = {p.name for p in SKILLS.iterdir() if p.is_dir()}
        for path in SKILLS.glob("*/SKILL.md"):
            for named in re.findall(r"the skill \**([a-z0-9-]+)\**", path.read_text()):
                with self.subTest(skill=path.parent.name, names=named):
                    self.assertIn(named, names)

    def test_every_skill_ends_in_a_pull_request_never_a_deploy(self):
        for path in SKILLS.glob("*/SKILL.md"):
            text = path.read_text()
            with self.subTest(skill=path.parent.name):
                if path.parent.name != "pull-request-from-databricks":
                    self.assertIn("pull-request-from-databricks", text, "changes reach a workspace only through a pull request")
                self.assertNotRegex(text, r"tf\.sh \S+ apply|bundle deploy|ALLOW_LOCAL_APPLY=1", "never deploy by hand")


if __name__ == "__main__":
    unittest.main()
