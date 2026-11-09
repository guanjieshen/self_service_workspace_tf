# AI review evaluation cases

Each `<name>.json` is a pull request a platform admin might see, and what a careful reviewer
would conclude about it. `scripts/ai-review-eval.py` runs the real review (the prompt in
`../plan-review-prompt.md`, the model in `config/setup.yaml`) on every case and checks the
answers; read the answers it writes to `.ai-eval/` too, because a passing check is not the
same as a helpful answer.

```bash
az login                                   # or --profile <a Databricks CLI profile>
python3 scripts/ai-review-eval.py          # every case
python3 scripts/ai-review-eval.py --case resize --repeat 3   # one case, three times (stability)
```

Run it after every change to the prompt or to what the review is given. A change that fixes
one case must not break another.

## A case

| Key | What it is |
| --- | --- |
| `description` | The pull request, in one sentence |
| `expected_risk` | The levels a careful reviewer could give it (`Low`, `Medium`, `High`) |
| `must_mention` | Groups of words; the answer must contain at least one word of each group |
| `must_not_mention` | Words that would make the answer wrong or misleading |
| `state` | `first` (a first apply) or `update` |
| `workspace`, `changed_files`, `config_diff`, `workspace_file`, `plan_guard`, `preflight` | The review's inputs, as CI would give them |
| `plan` or `plan_file` | The plan's `resource_changes` (from `terraform show -json`), inline or in a file here |

The review sees the baseline the Terraform tests use (`terraform/tests/defaults/`), so a
case does not change when an organization changes its own baseline.

## Adding a case

Add a case for every behaviour you change or fix in the prompt: the pull request that
showed the problem, and the conclusion a person would reach. Keep plans small and real:
copy resource shapes from `new-workspace.plan.json`.

`new-workspace.plan.json` is a real first-apply plan, against the test baseline, with the
sandbox's identifiers replaced. To make a new one: in a scratch copy of the repository,
copy `terraform/tests/defaults/` over `config/defaults/` (with a real `account_id`), remove
`config/backend.hcl` (local state), run `./scripts/tf.sh <workspace> plan` against a
workspace you may read, and take `.plans/<workspace>.json`.
