"""install/copy_to_your_repo.py: copying a release into an organization's repository, which may
already hold files from its template."""
import importlib.util
import pathlib
import tempfile
import unittest

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
                            ".gitignore": ".terraform/\n.state/\n", ".github/CODEOWNERS": "* @your-org/databricks-platform\n",
                            ".github/workflows/deploy.yml": "name: Deploy\n", ".git/config": "[core]\n"})
        # What an organization's template might already hold.
        write(self.target, {"README.md": "template readme\n", "LICENSE": "proprietary\n", ".gitignore": ".terraform/\n*.log\n",
                            ".github/CODEOWNERS": "* @enterprise/required-reviewers\n",
                            ".github/workflows/codeql.yml": "name: CodeQL\n", ".git/config": "[theirs]\n"})

    def tearDown(self):
        self.tmp.cleanup()

    def test_preview_tells_what_happens_to_each_file(self):
        actions = inst.plan(self.source, self.target)
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
        actions = inst.plan(self.source, self.target)
        inst.copy(self.source, self.target, actions)
        self.assertEqual((self.target / "README.md").read_text(), "ours\n")
        self.assertEqual((self.target / "LICENSE").read_text(), "proprietary\n")
        self.assertEqual((self.target / ".github/workflows/deploy.yml").read_text(), "name: Deploy\n")
        ignore = (self.target / ".gitignore").read_text()
        self.assertIn(".state/", ignore)
        self.assertIn("*.log", ignore, "their ignore rules stay")
        self.assertEqual(ignore.count(".terraform/"), 1)
        self.assertEqual((self.target / ".git/config").read_text(), "[theirs]\n")
        self.assertTrue(all(a in ("same", "keep") for a in inst.plan(self.source, self.target).values()),
                        "a second run has nothing left to do")

    def test_wrong_folders_are_refused(self):
        self.assertEqual(inst.check(self.source, self.target), [])
        self.assertTrue(inst.check(self.target, self.source), "the target is not a release")
        self.assertTrue(inst.check(self.source, self.source / "sub"), "the target inside the source")
        self.assertTrue(inst.check(self.source, pathlib.Path(self.tmp.name, "missing")))


if __name__ == "__main__":
    unittest.main()
