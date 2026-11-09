"""scripts/ai-review-eval.py: every case is well formed, builds a request, and the checks work."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from helpers import ROOT, load

ev = load("ai-review-eval")
CASES = sorted(p.stem for p in (ROOT / ".github/ai/eval").glob("*.json") if not p.name.endswith(".plan.json"))
GOOD = """**🟢 Low risk: the default warehouse gets bigger**
SS1 Default Warehouse in this workspace grows from X-Small to Small: more capacity, nothing removed.

### What's changing?
| Setting | Before | After |
|---|---|---|
| SS1 Default Warehouse size | X-Small | Small |"""


class Cases(unittest.TestCase):
    def test_there_are_cases_at_every_level(self):
        levels = {lvl for n in CASES for lvl in ev.load(n)["expected_risk"]}
        self.assertEqual(levels, {"Low", "Medium", "High"})

    def test_every_case_builds_a_request(self):
        for name in CASES:
            with self.subTest(case=name):
                case = ev.load(name)
                self.assertTrue(set(case["expected_risk"]) <= set(ev.LEVELS))
                self.assertTrue(all(isinstance(g, list) and g for g in case["must_mention"]))
                inputs = ev.inputs_for(case)
                self.assertTrue(inputs["planned_changes"], "the plan has changes")
                user = ev.review.build_request(inputs)["messages"][1]["content"]
                for tag in ev.review.SECTIONS:
                    self.assertIn(f"<{tag}>", user)

    def test_no_sandbox_identifiers(self):
        for f in (ROOT / ".github/ai/eval").glob("*.json"):
            text = f.read_text()
            for word in ("7405", "ccb842e7", "guanjie", "databricks.com"):
                self.assertNotIn(word, text, f"{f.name} holds a real identifier")


class Checks(unittest.TestCase):
    def test_a_good_answer_passes_and_a_wrong_level_fails(self):
        case = {"expected_risk": ["Low"], "must_mention": [["SS1 Default Warehouse"]], "must_not_mention": ["break"]}
        self.assertTrue(all(ok for _, ok, _ in ev.check(case, GOOD)))
        bad = {c: ok for c, ok, _ in ev.check({**case, "expected_risk": ["High"]}, GOOD)}
        self.assertFalse(bad["risk level"])

    def test_format_and_generic_advice_are_caught(self):
        case = {"expected_risk": ["Low"], "must_mention": [], "must_not_mention": []}
        results = {c: ok for c, ok, _ in ev.check(case, "Risk: Low. Please review carefully.")}
        self.assertFalse(results["risk summary"])
        self.assertFalse(results["what's changing"])
        self.assertFalse(results["avoids 'review carefully'"])
        # What the comment shows itself, and the sections a Medium or High answer needs.
        high = GOOD.replace("🟢 Low", "🔴 High") + "\nAdd the label allow-risky-changes."
        results = {c: ok for c, ok, _ in ev.check({**case, "expected_risk": ["High"]}, high)}
        self.assertFalse(results["leaves 'allow-risky-changes' to the comment"])
        self.assertFalse(results["### What should you review?"])


if __name__ == "__main__":
    unittest.main()


class Running(unittest.TestCase):
    """run() and main() with a stand-in for the model: what the evaluation does without a workspace."""

    def setUp(self):
        (ROOT / ".ai-eval").mkdir(exist_ok=True)   # git ignores it; the script names its folder from the root
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / ".ai-eval")
        self.patches = [mock.patch.object(ev, "OUT", ev.pathlib.Path(self.tmp.name)),
                        mock.patch.object(ev.review, "load_settings", return_value={"endpoint": "a-model", "host": ""})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_a_case_is_asked_and_its_answer_kept_and_checked(self):
        with mock.patch.object(ev.review, "model_review", return_value=GOOD) as ask:
            name, attempt, results = ev.run(CASES[0], "a-model", 2)
        self.assertEqual(ask.call_args[0][0], "a-model")
        self.assertEqual((ev.pathlib.Path(self.tmp.name) / f"{CASES[0]}.2.md").read_text(), GOOD + "\n", "each attempt kept apart")
        self.assertEqual((name, attempt), (CASES[0], 2))
        self.assertTrue(any(c == "risk level" for c, _, _ in results))

    def test_main_reports_each_case_and_needs_a_review_workspace(self):
        out = io.StringIO()
        with mock.patch.object(ev.review, "model_review", return_value=GOOD), mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch("sys.argv", ["ai-review-eval.py", "--case", CASES[0], "--host", "https://review.example.com"]), \
                contextlib.redirect_stdout(out):
            ev.main()
        self.assertRegex(out.getvalue(), rf"(PASS|FAIL)  {CASES[0]}")
        self.assertRegex(out.getvalue(), r"\n[01]/1 passed\. Answers in \.ai-eval/")
        with mock.patch("sys.argv", ["ai-review-eval.py", "--case", CASES[0]]), mock.patch.dict(os.environ, {}, clear=False), \
                self.assertRaisesRegex(SystemExit, "No review workspace"):
            os.environ.pop("DATABRICKS_HOST", None)
            ev.main()

