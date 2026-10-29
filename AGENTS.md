# AGENTS.md

Guidance for coding agents (and people) working in this repository. Read this first, then
the guide in [`agents/`](agents/) for what you are changing. All agent guidance lives in that
folder; the AGENTS.md files in `terraform/` and `config/` only point to it.

| You are changing | Read |
| --- | --- |
| `terraform/` (modules, checks, tests, the job notebooks) | [agents/terraform.md](agents/terraform.md) |
| `config/` (an organization's settings) | [agents/config.md](agents/config.md) |

Add a new guide to `agents/` and to this table; don't start a new AGENTS.md elsewhere.

## What this repository is

A governed baseline for Databricks citizen development workspaces, run from Git:
`config/` (YAML) plus `terraform/`, one Terraform state per workspace, applied by CI.
What people request (schemas, workspace folders) belongs to the self-service app, not
to this repository.


Two kinds of repository use this code:

- **The framework repository** (this one, with `dev/`): the maintainers change anything.
- **An organization's instance** (installed from a release tag, without `dev/`): the organization edits **only** `config/` and `.github/CODEOWNERS`.
  Everything else is the framework and is replaced on upgrade (README.md, "Installing and
  upgrading"). In an instance, a fix to framework code goes to the framework maintainers.

## Where things are

| You want to | Look at |
| --- | --- |
| Understand what it does and why | `DESIGN.md` (purpose, config model, access model, catalog, caveats) |
| Change a workspace's configuration | `config/README.md`, `agents/config.md` |
| Add a workspace | `python3 scripts/workspaces.py new <name> --bu ... --lob ... --host ... --account-id ...` |
| Add or change a Terraform option | `agents/terraform.md` |
| Set up an organization's instance | `docs/SETUP.md` (by team), `config/setup.yaml`, `scripts/setup.py`, `scripts/preflight.py`; CI details in `docs/github-actions.md` |
| See ideas not built | `docs/future.md` |
| See what changed | `CHANGELOG.md` (keep its Unreleased section current) |

## Where it runs: an organization's GitHub, deployed only by GitHub Actions

This repository is installed into the customer's own GitHub (an organization's instance,
above), and **everything reaches their workspaces through GitHub Actions**: with the
one-time setup in `docs/github-actions.md` done and the configuration right, a merged pull
request deploys everything with no further step. When you add something:

- **Make Terraform or a workflow do it.** A step someone must run by hand (a CLI command, a
  click in a UI, a script on a laptop) is a bug unless no API can do it, or a person must
  decide it by design.
- **If it cannot be automated, say so** in `docs/github-actions.md` ("What GitHub Actions does
  not do") and `docs/SETUP.md`, with who does it, when and how; script it in
  `scripts/setup.py` if a command can do it; and fail early with a message naming that step
  (a check in `scripts/preflight.py` for something in the workspace, a precondition in
  `terraform/checks.tf` for the configuration) rather than half-way through an apply.
- **Never depend on this repository's own setup:** not a CLI profile, a laptop, `dev/`, the
  sandbox's names or IDs, or a person's account. Identities come from Terraform outputs and
  repository variables.

## Rules

1. **Changes reach a workspace only through a merged pull request.** The Plan workflow
   plans every affected workspace on the PR; the Apply workflow applies on merge to
   `main`. `scripts/tf.sh apply` and `destroy` refuse outside GitHub Actions
   (`ALLOW_LOCAL_APPLY=1` is break-glass for a human, not for an agent). Never push to
   `main` directly and never add a manual trigger to Apply.
2. **Never bypass git hooks** (`--no-verify`, `-n`, `core.hooksPath`). If a hook fails,
   fix the cause.
3. **Do not handle secrets.** Never create, print or export tokens or client secrets;
   CI signs in with GitHub OIDC (Entra). Locally, sign in with the Azure or Databricks CLI.
4. **Grant to groups, never to people.**
5. **Leaving a setting alone releases it; it never destroys it.** `null` in YAML means
   "Terraform leaves this alone": `tf.sh` removes it from the state before apply, because
   destroying a Databricks setting resets it. Keep that property in anything you add.
6. **Every change ships with tests** (below). A new option comes with a fixture and an
   assertion; a new check with a fixture that fails it.
7. **Keep it simple.** This was deliberately cut down (fewer workflows, fewer options,
   plain YAML). Prefer removing a feature to adding a switch; prefer a short, readable
   script to a framework.

## Test and ship

```bash
./scripts/test.sh                # everything, no workspace or credentials needed
./scripts/test.sh terraform      # or one suite: terraform | python | node | scaffold
```

- `terraform`: `terraform/tests/*.tftest.hcl` with mocked providers and fixture workspaces.
- `python`: `scripts/tests/` (standard library only).
- CI runs the same suites in the **Tests** check, then plans each affected workspace and
  posts the plan, an AI review and the plan guard's findings on the PR.

Before a PR: run the suites you touched and `terraform fmt -recursive terraform`. After a
merge: watch the Apply run, and check the result in the workspace (read-only) if it
changed something visible.

**The plan guard** (`scripts/plan-guard.py`) fails a plan with hard-to-undo or
security-weakening changes until a person adds the PR label `allow-risky-changes`. Do not
add that label yourself; say what the plan does and let a person decide.

## Writing style

- Plain words in code comments, error messages and docs. Say what
  happens and why, for someone who has not read the code.
- Comments explain why, not what. Match the comment density of the file you are in.
- Error messages from checks name the setting, the file and what to do.
- README-style docs: no em dashes; short sections; tables for options.

## Gotchas learned the hard way

- **State lock collisions.** Two CI runs on the same workspace (a PR plan and an Apply)
  collide on the state lock: "state blob is already locked". Re-run the failed one. Do
  not run local plans while CI plans or applies.
- **A hook false positive** can block a command that has `git commit` together with
  short flags such as `grep -n` or `sed -n`. Run the commit as its own command.
- **Stacked PRs:** always target `main`. Deleting a merged base branch closes PRs stacked
  on it.
- **Workspace-local groups** cannot be used in Unity Catalog grants or usage policies;
  the persona groups must be account groups (synced from Entra ID).
- **One service principal, two federated credentials.** CI signs in as `pull_request` (Plan)
  or `ref:refs/heads/main` (Apply, Drift). Never put a job that signs in into a GitHub
  Environment: its subject becomes `environment:<name>` and sign-in fails. `apply-approval`
  is only the approval step (`scripts/tests/test_setup.py` checks this).
- **Local plans as a person** can show permission drift that CI does not (different
  identity). Trust CI's plan and drift check.
- **Run tests through `scripts/test.sh`.** Plain `terraform test` in `terraform/` fails on a
  missing provider; `./scripts/test.sh terraform` sets the plugin directory (TF_DATA_DIR).
- **GitHub's UI lags.** A job can show "in progress" after its steps finished, and Apply can sit
  queued for minutes after a merge. Wait (`gh run watch`); re-running it collides on the state lock.
- More provider-specific gotchas: `agents/terraform.md`.
