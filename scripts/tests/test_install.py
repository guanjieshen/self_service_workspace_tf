"""install/copy_to_your_repo.py: copying this repository (a clone of main, or a release branch)
into an organization's repository, which may already hold files from its template, without this
repository's own environment."""
import importlib.util
import pathlib
import tempfile
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("copy_to_your_repo", ROOT / "install/copy_to_your_repo.py")
inst = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inst)            # no dbutils here: only the functions are defined


def write(root, files):
    for path, text in files.items():
        p = pathlib.Path(root) / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source, self.target = pathlib.Path(self.tmp.name, "source"), pathlib.Path(self.tmp.name, "target")
        write(self.source, {"VERSION": "v1.0.0\n", "scripts/tf.sh": "#!/usr/bin/env bash\n", "README.md": "ours\n",
                            "scripts/release.py": (ROOT / "scripts/release.py").read_text(),
                            "scripts/workspaces.py": (ROOT / "scripts/workspaces.py").read_text(),
                            ".gitignore": ".terraform/\n.state/\n", ".github/CODEOWNERS": "* @your-org/databricks-platform\n",
                            ".github/workflows/deploy.yml": "name: Deploy\n", ".git/config": "[core]\n"})
        # What an organization's template might already hold.
        write(self.target, {"README.md": "template readme\n", "LICENSE": "proprietary\n", ".gitignore": ".terraform/\n*.log\n",
                            ".github/CODEOWNERS": "* @enterprise/required-reviewers\n",
                            ".github/workflows/codeql.yml": "name: CodeQL\n", ".git/config": "[theirs]\n"})

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self):
        self.release = inst.released(self.source)
        return inst.plan(self.source, self.target, self.release)

    def copy(self, actions):
        return inst.copy(self.target, actions, self.release)

    def test_preview_tells_what_happens_to_each_file(self):
        actions = self.plan()
        self.assertEqual(actions["VERSION"], "new")
        self.assertEqual(actions["README.md"], "replace")
        self.assertEqual(actions[".gitignore"], "merge")
        self.assertEqual(actions["LICENSE"], "keep", "their files are never deleted")
        self.assertNotIn(".git/config", actions, "git's own folder is never copied or compared")
        text = inst.report(actions, self.target)
        self.assertIn("@enterprise/required-reviewers", text, "their CODEOWNERS is shown before it is replaced")
        self.assertIn(".github/workflows/codeql.yml", text, "their workflows keep running: say so")
        self.assertEqual((self.target / "README.md").read_text(), "template readme\n", "preview writes nothing")

    def test_copy_writes_the_release_and_keeps_theirs(self):
        actions = self.plan()
        self.copy(actions)
        self.assertEqual((self.target / "README.md").read_text(), "ours\n")
        self.assertEqual((self.target / "LICENSE").read_text(), "proprietary\n")
        self.assertEqual((self.target / ".github/workflows/deploy.yml").read_text(), "name: Deploy\n")
        ignore = (self.target / ".gitignore").read_text()
        self.assertIn(".state/", ignore)
        self.assertIn("*.log", ignore, "their ignore rules stay")
        self.assertEqual(ignore.count(".terraform/"), 1)
        self.assertEqual((self.target / ".git/config").read_text(), "[theirs]\n")
        self.assertTrue(all(a in ("same", "keep") for a in self.plan().values()),
                        "a second run has nothing left to do")

    def test_a_file_that_cannot_be_read_is_skipped_before_anything_is_written(self):
        # In a Git folder this notebook is a workspace object, which cannot be read as bytes.
        unreadable = self.source / "install/copy_to_your_repo"
        write(self.source, {"install/copy_to_your_repo": "notebook"})
        real = inst.readable
        with unittest.mock.patch.object(inst, "readable", lambda p: p != unreadable and real(p)):
            actions = self.plan()
            self.assertEqual(actions["install/copy_to_your_repo"], "skip")
            self.copy(actions)
        self.assertFalse((self.target / "install/copy_to_your_repo").exists())
        self.assertEqual((self.target / "VERSION").read_text(), "v1.0.0\n", "the rest is copied")

    def test_this_repositorys_environment_is_never_copied(self):
        # A clone of main: this repository's own workspaces, state, hub and owners.
        write(self.source, {
            "config/workspaces/sandbox.yaml": "prefix: sbx\nhost: https://adb-1234567890123456.7.azuredatabricks.net\n",
            "config/workspaces/_example.yaml": "prefix: fin\n", "config/backend.hcl": 'storage_account_name = "ourstate1"\n',
            "dev/notes.md": "ours\n", "config/setup.yaml": "tenant_id: 11111111-2222-3333-4444-555555555555   # Entra tenant\n",
            "config/self-service/hub.yaml": "hub:\n  name: our_hub\n  host: https://adb-9999999999999999.1.azuredatabricks.net\n",
            ".github/CODEOWNERS": "* @our-team\n"})
        (self.source / "VERSION").unlink()   # main has no VERSION
        actions = self.plan()
        for path in ("config/workspaces/sandbox.yaml", "config/backend.hcl", "dev/notes.md"):
            self.assertEqual(actions[path], "skip", path)
        self.assertEqual(actions["config/workspaces/_example.yaml"], "new")
        self.copy(actions)
        self.assertIn("tenant_id: null", (self.target / "config/setup.yaml").read_text())
        hub = (self.target / "config/self-service/hub.yaml").read_text()
        self.assertNotIn("our_hub", hub)
        self.assertNotIn("adb-9999", hub)
        self.assertEqual((self.target / ".github/CODEOWNERS").read_text(), "* @your-org/databricks-platform\n")
        self.assertEqual((self.target / "VERSION").read_text(), "main\n", "a clone of main says so")
        self.assertFalse((self.target / "config/workspaces/sandbox.yaml").exists())

    def test_an_identifier_left_anywhere_stops_the_copy(self):
        write(self.source, {"config/workspaces/sandbox.yaml": "prefix: sbx\nhost: https://adb-1234567890123456.7.azuredatabricks.net\n",
                            "docs/notes.md": "Our hub: https://adb-1234567890123456.7.azuredatabricks.net\n"})
        with self.assertRaisesRegex(ValueError, "docs/notes.md: https://adb-1234567890123456"):
            inst.released(self.source)
        self.assertFalse((self.target / "docs").exists(), "nothing was written")

    def test_what_git_ignores_and_git_itself_are_never_copied(self):
        write(self.source, {".gitignore": ".terraform/\n*.tfstate\n", "bundle/.gitignore": "build/\n",
                            ".terraform/providers/x": "cache", "terraform/a.tfstate": "state",
                            "bundle/hub/build/config.json": '{"host": "https://adb-1234567890123456.7.azuredatabricks.net"}',
                            "bundle/hub/databricks.yml": "bundle: {}\n", "vendor/lib/.git": "gitdir: /elsewhere\n"})
        actions = self.plan()
        for path in (".terraform/providers/x", "terraform/a.tfstate", "bundle/hub/build/config.json", "vendor/lib/.git"):
            self.assertNotIn(path, actions, f"{path}: not part of the repository")
        self.assertEqual(actions["bundle/hub/databricks.yml"], "new")

    def test_an_upgrade_keeps_your_configuration_and_drops_what_the_framework_removed(self):
        write(self.source, {"config/defaults/compute.yaml": "size: Medium\n", "config/README.md": "new docs\n",
                            "config/defaults/new_feature.yaml": "new_feature: {enabled: true}\n",
                            "config/self-service/app.yaml": "title: Self-Service\n", "scripts/new.py": "new\n"})
        write(self.target, {"VERSION": "v1.0.0\n",   # an installed copy: this is an upgrade
                            "config/defaults/compute.yaml": "size: Small   # ours\n", "config/README.md": "old docs\n",
                            "config/self-service/app.yaml": "title: Our portal\n", "config/workspaces/hr.yaml": "prefix: hr\n",
                            "scripts/retired.py": "old\n", ".github/workflows/codeql.yml": "name: CodeQL\n"})
        actions = self.plan()
        self.assertEqual(actions["config/defaults/compute.yaml"], "yours", "your baseline is never replaced")
        self.assertEqual(actions["config/self-service/app.yaml"], "yours")
        self.assertEqual(actions[".github/CODEOWNERS"], "yours")
        self.assertEqual(actions["config/workspaces/hr.yaml"], "keep")
        self.assertEqual(actions["config/README.md"], "replace", "the framework's own files under config/ are replaced")
        self.assertEqual(actions["scripts/retired.py"], "remove", "a framework file the new version dropped")
        self.assertEqual(actions["config/defaults/new_feature.yaml"], "baseline", "a new baseline file is yours to add")
        self.assertEqual(actions[".github/workflows/codeql.yml"], "keep", "your own workflows are never removed")
        self.copy(actions)
        self.assertEqual((self.target / "config/defaults/compute.yaml").read_text(), "size: Small   # ours\n")
        self.assertFalse((self.target / "scripts/retired.py").exists())
        self.assertFalse((self.target / "config/defaults/new_feature.yaml").exists())
        self.assertEqual((self.target / "scripts/new.py").read_text(), "new\n")
        self.assertEqual((self.target / "VERSION").read_text(), (self.source / "VERSION").read_text(), "the new version")

    def test_a_clone_says_which_commit_it_copied(self):
        (self.source / "VERSION").unlink()          # main has no VERSION
        write(self.source, {".git/HEAD": "ref: refs/heads/main\n", ".git/refs/heads/main": "5569f87abcdef0123456789\n"})
        self.assertEqual(inst.source_version(self.source), "main @ 5569f87")
        (self.source / ".git/refs/heads/main").unlink()   # after git gc: in packed-refs
        write(self.source, {".git/packed-refs": "# pack-refs with: peeled\n0b1c2d3e4f5a refs/heads/main\n"})
        self.assertEqual(inst.source_version(self.source), "main @ 0b1c2d3")
        write(self.source, {".git/HEAD": "9f8e7d6c5b4a\n"})       # a detached checkout
        self.assertEqual(inst.source_version(self.source), "main @ 9f8e7d6")
        self.assertEqual(inst.source_version(self.target / "nowhere"), "main", "no .git to read (a Databricks Git folder)")
        self.copy(self.plan())
        self.assertEqual((self.target / "VERSION").read_text(), "main @ 9f8e7d6\n")

    def test_your_workspace_files_are_never_touched_even_on_a_first_install(self):
        # Theirs, before the first copy; one named like one of this repository's own.
        write(self.target, {"config/workspaces/hr.yaml": "prefix: hr   # ours\n",
                            "config/workspaces/sandbox.yaml": "prefix: theirs\n"})
        write(self.source, {"config/workspaces/sandbox.yaml": "prefix: sbx\nhost: https://adb-1234567890123456.7.azuredatabricks.net\n",
                            "config/workspaces/_example.yaml": "prefix: xyz\n"})
        actions = self.plan()
        self.assertEqual(actions["config/workspaces/hr.yaml"], "keep")
        self.assertEqual(actions["config/workspaces/sandbox.yaml"], "keep", "this repository's is never copied, so theirs stays")
        self.copy(actions)
        self.assertEqual((self.target / "config/workspaces/sandbox.yaml").read_text(), "prefix: theirs\n")
        self.assertEqual((self.target / "config/workspaces/hr.yaml").read_text(), "prefix: hr   # ours\n")

    def test_wrong_folders_are_refused(self):
        self.assertEqual(inst.check(self.source, self.target), [])
        self.assertTrue(inst.check(self.target, self.source), "the source is not this repository")
        self.assertTrue(inst.check(self.source, self.source / "sub"), "the target inside the source")
        self.assertTrue(inst.check(self.source, pathlib.Path(self.tmp.name, "missing")))


if __name__ == "__main__":
    unittest.main()
