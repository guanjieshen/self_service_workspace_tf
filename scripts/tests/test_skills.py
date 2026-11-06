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
                              "change-one-workspace", "update-self-service-app", "upgrade-to-a-new-release", "change-genie-code"}, names)

    def test_each_is_a_folder_with_a_well_formed_skill(self):
        for folder in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
            with self.subTest(skill=folder.name):
                meta = front_matter(folder / "SKILL.md")
                self.assertEqual(meta.get("name"), folder.name, "the front matter's name is the folder's")
                self.assertRegex(folder.name, r"^[a-z0-9]+(-[a-z0-9]+)*$", "lowercase words and dashes")
                description = meta.get("description", "")
                self.assertTrue(description.startswith("Use when"), "say when to use it: Genie Code matches on it")
                # The front matter is YAML (Genie Code and GitHub read it): an unquoted value with ": " or " #"
                # in it is not valid YAML, and the skill may not load.
                for key, value in meta.items():
                    self.assertNotRegex(value, r": | #", f"{key}: no ': ' or ' #' in it (YAML); use a comma or a full stop")
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



class AppSkillCoversTheApp(unittest.TestCase):
    """update-self-service-app is how an admin finds a setting: every Settings tab and every key of
    config/self-service/app.yaml that an admin may change is in it, so a new one cannot be missed."""
    SKILL = (SKILLS / "update-self-service-app/SKILL.md").read_text()
    # Keys an admin is never sent to: they name the apps and the database (the skill says never to
    # change them), or are details of a setting the skill already names.
    NOT_FOR_ADMINS = {"name", "approvals", "database", "admin_path", "require_request_record", "personal_schema", "temporary_schema"}

    def test_every_settings_tab_is_in_it(self):
        settings = (ROOT / "apps/self-service/settings.py").read_text()
        tabs = re.search(r"TABS = \[(.*?)\n\]", settings, re.S).group(1)
        for label in re.findall(r'\("[a-z_]+", "([^"]+)"', tabs):
            with self.subTest(tab=label):
                self.assertTrue(f"**{label}**" in self.SKILL, f"Settings tab {label}: say in the skill what it holds")

    def test_every_app_yaml_key_an_admin_changes_is_in_it(self):
        text = (ROOT / "config/self-service/app.yaml").read_text()
        for block in ("self_service_app", "jobs"):
            body = re.search(rf"(?ms)^{block}:\n(.*?)(?=^\S|\Z)", text).group(1)
            for key in re.findall(r"(?m)^  ([a-z_]+):", body):
                if key in self.NOT_FOR_ADMINS:
                    continue
                with self.subTest(block=block, key=key):
                    self.assertTrue(f"`{key}" in self.SKILL, f"app.yaml {block}.{key}: say in the skill when an admin changes it")


if __name__ == "__main__":
    unittest.main()
