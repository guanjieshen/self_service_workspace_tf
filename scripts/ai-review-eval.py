#!/usr/bin/env python3
"""Run the AI plan review on the evaluation cases, and check each answer.

    scripts/ai-review-eval.py [--case <name> ...] [--repeat N] [--model <name>] [--host <url>] [--profile <p>]

Each case in .github/ai/eval/<name>.json is a pull request a platform admin might see: its
config diff, the workspace's file, the plan, the plan guard's and preflight's findings, and
what a careful reviewer would conclude (expected_risk, facts the answer must mention, words it
must not use). The runner builds the same request CI does (scripts/ai-plan-review.py,
build_request) against the baseline the Terraform tests use (terraform/tests/defaults/), calls
the model in the review workspace (config/setup.yaml ai_review_host and ai_review_model, or
--host / --model), and checks:

  - format: the risk line, the table header, the check section, the length;
  - risk: the level is one of expected_risk;
  - content: every must_mention group has a match; no must_not_mention word appears.

The answers are written to .ai-eval/<case>.md, to read: the checks catch regressions, a person
judges whether the answer is genuinely useful. Run it after any change to the prompt
(.github/ai/plan-review-prompt.md) or to what the review is given. Needs the Databricks CLI,
signed in to the review workspace (locally: az login, or --profile).
"""
import argparse
import concurrent.futures
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASES = ROOT / ".github/ai/eval"
OUT = ROOT / ".ai-eval"
PINNED = ROOT / "terraform/tests/defaults"
MAX_WORDS = 250                       # Medium and High: the prompt asks for under 220; slack for tables
MAX_WORDS_LOW = 120                   # Low: the prompt asks for under 90
MAX_WORDS_FIRST = 290                 # a first apply: the table lists a whole baseline
LEVELS = ("Low", "Medium", "High")
GENERIC = ["review carefully", "test first", "double-check", "as always", "attack surface",
           "potential security implications", "best practices", "critical", "dangerous"]

sys.path.insert(0, str(ROOT / "scripts"))
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("ai_plan_review", ROOT / "scripts/ai-plan-review.py")
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def load(name):
    case = json.loads((CASES / f"{name}.json").read_text())
    plan = json.loads((CASES / case["plan_file"]).read_text())["resource_changes"] if "plan_file" in case else case["plan"]
    case["resource_changes"] = plan
    return case


def inputs_for(case):
    baseline = "\n\n".join(f"# config/defaults/{f.name}\n{review.without_comments(f)}" for f in sorted(PINNED.glob("*.yaml")))
    state = ("First apply: Terraform manages nothing in this workspace yet, so the whole baseline is created."
             if case["state"] == "first" else "Update: Terraform already manages resources in this workspace.")
    return {
        "workspace": case["workspace"],
        "state": state,
        "changed_files": case["changed_files"],
        "config_diff": case["config_diff"],
        "code_diff": case.get("code_diff", "(no Terraform code or CHANGELOG changes in this pull request)"),
        "workspace_files": "# self_service_1.yaml\n" + case["workspace_file"],
        "baseline": baseline,
        "planned_changes": review.planned_changes({"resource_changes": case["resource_changes"]}),
        "plan_guard": case.get("plan_guard", ""),
        "preflight": case.get("preflight", ""),
    }


def check(case, answer):
    """[(check, passed, detail)]: the format the comment expects, the risk level, and the content."""
    out = []
    first = answer.lstrip().splitlines()[0] if answer.strip() else ""
    m = re.match(r"^\*\*(?:🟢|🟡|🔴) (Low|Medium|High) risk: .+\*\*$", first)
    level = m.group(1) if m else None
    out.append(("risk summary", m is not None, level or f"missing: {first[:60]!r}"))
    out.append(("risk level", level in case["expected_risk"], f"{level} (expected {'/'.join(case['expected_risk'])})"))
    out.append(("what's changing", "### What's changing?" in answer and re.search(r"(?m)^\|.*\|$", answer) is not None, ""))
    if level in ("Medium", "High"):
        for section in ("### What does this mean?", "### What should you review?"):
            out.append((section, section in answer, ""))
    words = len(re.findall(r"\w+", answer))
    limit = MAX_WORDS_LOW if level == "Low" else MAX_WORDS_FIRST if case.get("state") == "first" else MAX_WORDS
    out.append(("length", words <= limit, f"{words} words (at most {limit})"))
    # What the comment around the review shows: never repeated by it.
    for word in ("allow-risky-changes", "Before merging", "<details", "AI-generated", "module.", "!!!"):
        out.append((f"leaves '{word}' to the comment", word not in answer, ""))
    low = answer.lower()
    for group in case["must_mention"]:
        out.append((f"mentions {' / '.join(group)}", any(g.lower() in low for g in group), ""))
    for word in case.get("must_not_mention", []) + GENERIC:
        out.append((f"avoids '{word}'", word.lower() not in low, ""))
    return out


def run(name, model, attempt):
    case = load(name)
    request = review.build_request(inputs_for(case))
    answer = review.model_review(model, request)
    OUT.mkdir(exist_ok=True)
    suffix = f".{attempt}" if attempt else ""
    (OUT / f"{name}{suffix}.md").write_text(answer + "\n")
    return name, attempt, check(case, answer)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", action="append", help="a case name (default: every case)")
    ap.add_argument("--repeat", type=int, default=1, help="run each case N times, to see how stable it is")
    ap.add_argument("--model")
    ap.add_argument("--host")
    ap.add_argument("--profile")
    args = ap.parse_args()
    settings = review.load_settings()
    model = args.model or settings["endpoint"]
    if args.profile:
        os.environ["DATABRICKS_CONFIG_PROFILE"] = args.profile
    else:
        os.environ["DATABRICKS_HOST"] = args.host or settings["host"]
        if not os.environ["DATABRICKS_HOST"]:
            raise SystemExit("No review workspace: set ai_review_host in config/setup.yaml, or pass --host")
    names = args.case or sorted(p.stem for p in CASES.glob("*.json") if not p.name.endswith(".plan.json"))
    jobs = [(n, a) for n in names for a in range(args.repeat if args.repeat > 1 else 1)]
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for name, attempt, results in pool.map(lambda j: run(j[0], model, j[1] if args.repeat > 1 else 0), jobs):
            bad = [r for r in results if not r[1]]
            failed += bool(bad)
            label = f"{name}{f' #{attempt}' if args.repeat > 1 else ''}"
            risk = next(r[2] for r in results if r[0] == "risk level")
            print(f"{'PASS' if not bad else 'FAIL'}  {label:32} risk {risk}")
            for c, _, detail in bad:
                print(f"        failed: {c} {detail}")
    print(f"\n{len(jobs) - failed}/{len(jobs)} passed. Answers in {OUT.relative_to(ROOT)}/.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
