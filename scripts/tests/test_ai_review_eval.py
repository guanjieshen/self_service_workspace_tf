"""scripts/ai-review-eval.py: every case is well formed, builds a request, and the checks work."""
import json
import unittest

from helpers import ROOT, load

ev = load("ai-review-eval")
CASES = sorted(p.stem for p in (ROOT / ".github/ai/eval").glob("*.json") if not p.name.endswith(".plan.json"))
GOOD = """**Risk:** 🟢 **Low**: the default warehouse grows; nothing is removed.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | SS1 Default Warehouse | X-Small → Small | explorers, builders |

#### Check before merging
Nothing stands out."""


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
        self.assertFalse(results["risk line"])
        self.assertFalse(results["table"])
        self.assertFalse(results["avoids 'review carefully'"])


if __name__ == "__main__":
    unittest.main()
