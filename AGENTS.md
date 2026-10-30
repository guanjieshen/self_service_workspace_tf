# Working on this repository

Guidance for **coding agents and people** changing the framework: the Terraform, the scripts, the workflows and the docs. If you only need to configure workspaces, start with the [README](README.md) and [config/README.md](config/README.md) instead.

> **Start here.** Read this file, then the guide for the folder you are changing. All agent guidance lives in [`agents/`](agents/); the AGENTS.md files in `terraform/` and `config/` only point to it.

| You are changing | Read |
| --- | --- |
| `terraform/` (root module, modules, checks, tests) | [agents/terraform.md](agents/terraform.md) |
| `config/` (an organization's settings) | [agents/config.md](agents/config.md) |
| `scripts/`, `.github/`, docs | This file |

## What this repository is

A governed baseline for Azure Databricks citizen development workspaces, run from Git:
YAML in `config/`, Terraform in `terraform/`, one state per workspace, planned on every pull
request and applied on merge by GitHub Actions. What people request (schemas, workspace
folders) belongs to the self-service app, in its own repository, not here.

Two kinds of repository use this code:

- **The framework repository** (this one, with `dev/`): maintainers change anything.
- **An organization's instance** (installed from a release, without `dev/`): the
  organization edits **only** `config/` and `.github/CODEOWNERS`. Everything else is the
  framework and is replaced on upgrade (`docs/SETUP.md`, "Upgrade to a new release"). In
  an instance, a fix to framework code goes to the framework maintainers.

## Where the docs are

Each topic has one home. Update that file; link to it from elsewhere instead of repeating it.

| File | For | Holds |
| --- | --- | --- |
| `README.md` | Everyone, first | What the project does, the Get started steps, the layout, links to the rest |
| `docs/SETUP.md` | The teams setting it up | Step by step from the zip to the first workspace, by team; day to day; upgrades; troubleshooting |
| `config/README.md` | Whoever changes the configuration | The workspace file, the merge rule and a task table: which key to set for what |
| `docs/user-journeys.md` | Everyone | The everyday journeys, step by step: add a workspace, change one or all, give access, retire one |
| `docs/design.md` | Maintainers, reviewers | Why it works the way it does: config model, access model, catalog, caveats, open questions, what is not built |
| `docs/github-actions.md` | Maintainers | The workflows: how CI signs in, which workspaces a change plans and applies, runners, the plan comment, who can run code with the credentials |
| `CHANGELOG.md` | Everyone upgrading | What changed in each release, and what the first plan after an upgrade shows |
| `AGENTS.md`, `agents/*.md` | Coding agents | How to change the project (this file), and one guide per folder |
| `config/defaults/*.yaml`, `config/setup.yaml` | Whoever edits them | The comment beside each key is its documentation |

## How to update this project

### The workflow

1. **Branch from `main`**; never commit to `main` directly. One topic per pull request.
2. **Change the code, its tests and its docs together** (the table below).
3. **Run the tests:** `./scripts/test.sh` (no workspace or credentials needed) and
   `terraform fmt -recursive terraform`.
4. **Open a pull request.** CI runs **Format and validate** and **Tests**, and the workflow
   of every workspace the change concerns plans it and posts the plan, the plan guard's
   findings and an AI review as a comment. Read the plan comment, not only the checks.
5. **Merge** when the checks pass and a person has read the plan. Each concerned
   workspace's workflow applies it. Watch them (`gh run watch`).

### What to change with what

| You change | Also change | Tests |
| --- | --- | --- |
| A baseline value in `config/defaults/` | The comment beside it; `CHANGELOG.md` if it changes what workspaces get | None, unless the shipped baseline changes: then the copy in `terraform/tests/defaults/` too |
| A new baseline key (an option) | The same key in `terraform/tests/defaults/`; its use in `terraform/`; `config/README.md` (task table) if operators set it; `CHANGELOG.md` (what the first plan shows) | A fixture under `terraform/tests/fixtures/` and an assertion (`agents/terraform.md`) |
| A Databricks setting | Map it in `terraform/overrides.tf` (`setting_addresses`) so `null` releases it | `scripts/tests/test_release.py` checks the mapping |
| A check (a wrong value fails the plan) | `terraform/checks.tf`: the message names the key, the file and what to do | A fixture under `terraform/tests/fixtures/invalid/` and a run in `validation.tftest.hcl` |
| A setup step or a manual step | `scripts/setup.py` if a command can do it, else the checklist in `docs/SETUP.md`; a `scripts/preflight.py` check if Terraform depends on it | `scripts/tests/test_setup.py`, `test_preflight.py` |
| A value in `config/setup.yaml` | `docs/SETUP.md` step 1 table; `OPTIONS` in `scripts/setup.py` (or `scripts/ai-plan-review.py` for `ai_review_host` and `ai_review_model`) | `test_setup.py` checks every key in the file is read |
| The AI review: its prompt (`.github/ai/plan-review-prompt.md`) or what it is given (`scripts/ai-plan-review.py`) | A case in `.github/ai/eval/` for the behaviour you change; run `python3 scripts/ai-review-eval.py` and read the answers in `.ai-eval/` | `scripts/tests/test_ai_review_eval.py` (cases well formed); the evaluation itself needs the review workspace |
| A workflow step | `.github/workflows/deploy.yml`; `docs/github-actions.md` | A job that signs in must not run in a GitHub Environment (`test_setup.py`) |
| What a change plans or applies | `EVERYTHING` and `PLAN_ONLY` in `scripts/workspaces.py`; `docs/github-actions.md` | `scripts/tests/test_workspaces.py` (`Affected`) |
| A new workspace key (in a workspace file, not the baseline) | `workspace_keys` in `terraform/config.tf`; `config/workspaces/_example.yaml`; the workspace keys table in `config/README.md` | A fixture and an assertion |
| Something removed or renamed | Every doc that mentions it (search the repository), and its tests and fixtures | The suite still passes with nothing skipped; `scripts/tests/test_docs.py` fails on a path in the docs or comments that no longer exists |

### Keep it simple

Simplicity and ease of use come first. Before adding an option, ask whether a fixed,
sensible behavior would do; prefer removing a feature to adding a switch, and a short
readable script to a framework. A value people must fill in is required only if it is a
fact about their environment or a decision they must make; everything else gets a
default.

## Where it runs: an organization's GitHub, deployed only by GitHub Actions

With the setup in `docs/SETUP.md` done, a merged pull request deploys everything with no
further step. When you add something:

- **Make Terraform or a workflow do it.** A step someone must run by hand is a bug unless no
  API can do it, or a person must decide it by design.
- **If it cannot be automated, say so** in `docs/SETUP.md`, with who does it, when and how,
  and fail early with a message naming that step (a check in `scripts/preflight.py` for
  something in the workspace, a precondition in `terraform/checks.tf` for the
  configuration) rather than half-way through an apply.
- **Never depend on this repository's own setup:** not a CLI profile, a laptop, `dev/`, the
  sandbox's names or IDs, or a person's account.

## Rules

1. **Changes reach a workspace only through a merged pull request.** `scripts/tf.sh apply`
   and `destroy` refuse outside GitHub Actions (`ALLOW_LOCAL_APPLY=1` is break-glass for a
   human, not for an agent). Never push to `main` directly and never add a manual trigger
   to Apply.
2. **Never bypass git hooks** (`--no-verify`, `-n`, `core.hooksPath`). If a hook fails,
   fix the cause.
3. **Do not handle secrets.** Never create, print or export tokens or client secrets;
   CI signs in with GitHub OIDC (Entra). Locally, sign in with the Azure or Databricks CLI.
4. **Grant to groups, never to people.**
5. **Leaving a setting alone releases it; it never destroys it.** `null` in YAML means
   "Terraform leaves this alone": `tf.sh` removes it from the state before apply, because
   destroying a Databricks setting resets it. Keep that property in anything you add.
6. **Every change ships with tests.** A new option comes with a fixture and an assertion;
   a new check with a fixture that fails it.
7. **The plan guard** (`scripts/plan-guard.py`) fails a plan with hard-to-undo or
   security-weakening changes until a person adds the label `allow-risky-changes`. Never
   add that label yourself; say what the plan does and let a person decide.

## Tests

```bash
./scripts/test.sh                # everything
./scripts/test.sh terraform      # or one suite: terraform | python | node | scaffold
```

- `terraform`: `terraform/tests/*.tftest.hcl`, mocked providers, fixture workspaces, and the
  pinned baseline in `terraform/tests/defaults/` (never the organization's `config/defaults/`).
- `python`: `scripts/tests/` (standard library only).
- `node`: the plan comment (`.github/scripts/tests/`).
- `scaffold`: a workspace file copied from `_example.yaml` and filled in plans.

## Writing style

Write for someone who has not read the code. The [README](README.md) is the model for every markdown file:

- **Lead with what matters.** Open with one or two sentences on what the page is for, and put a `> **New to …?**` or `> **Start here.**` callout where a reader needs a pointer.
- **Tables for anything with more than two parts:** steps (with who does them), paths, options, "You want to… / Where to make the change".
- **Bold the key phrase** in a sentence or a cell, not whole sentences.
- **Short sentences, plain words, sentence case headings.** Say what happens and why.
- **One home per topic.** Link to it instead of repeating it.

In code:

- Comments explain why, not what. Match the comment density of the file you are in.
- Error messages name the setting, the file and what to do.

## Gotchas learned the hard way

- **State lock.** Plans and drift checks run with `-lock=false` (a plan never writes the
  state), so they never collide with an apply. Applies lock, and run one at a time per
  workspace (`concurrency: apply-<ws>`). A local `tf.sh plan` locks: do not run one while
  CI applies.
- **A hook false positive** blocks a command that has `git commit` (or `git push`) together
  with short flags such as `grep -n`, `sed -n` or `az ... -n`. Run git as its own command.
- **Stacked PRs:** always target `main`. Deleting a merged base branch closes PRs stacked
  on it.
- **Workspace-local groups** cannot be used in Unity Catalog grants or usage policies;
  persona groups must be account groups (synced from Entra ID).
- **One service principal, two federated credentials.** CI signs in as `pull_request` (Plan)
  or `ref:refs/heads/main` (Apply, Drift). A job that signs in inside a GitHub Environment
  signs in as `environment:<name>` and fails. `apply-approval` is only the approval step.
- **Local plans as a person** can show permission drift that CI does not (different
  identity). Trust CI's plan and drift check.
- **Run tests through `scripts/test.sh`.** Plain `terraform test` in `terraform/` fails on a
  missing provider; the script sets the plugin directory (TF_DATA_DIR).
- **GitHub's UI lags.** A job can show "in progress" after its steps finished, and Apply can
  sit queued for minutes after a merge. Wait (`gh run watch`).
- Terraform and provider gotchas: `agents/terraform.md`.
