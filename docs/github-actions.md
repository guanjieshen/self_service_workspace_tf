# Automated deployment with GitHub Actions

How the workflows plan, apply, check for drift and retire workspaces, and how they sign in. Setting them up is [SETUP.md](SETUP.md), steps 4 and 5.

> **Just want to know what happens to your pull request?** See [The plan comment](#the-plan-comment) and [Hardening and noise](#hardening-and-noise).

## Overview

**One deploy workflow, one job per workspace.** `.github/workflows/deploy.yml` first works out
which workspaces a change concerns (`scripts/workspaces.py affected`), then runs one job for
each, in parallel on the runners there are, each with its own log and Re-run button.
`checks.yml` runs the pull request checks.

| Workflow | Runs on | Does |
| --- | --- | --- |
| `checks.yml` (**Format and validate**, **Tests**) | Every pull request | Formatting, `terraform validate`, the cross-workspace checks, every test. Required by branch protection |
| `deploy.yml`, on a pull request | The workspaces the change concerns (below) | For each: preflight, plan, and a plan comment (the plan, the plan guard's warnings, an AI review) when the plan changes something. A plan with hard-to-undo or security-weakening changes fails until someone adds the label `allow-risky-changes` |
| `deploy.yml`, on merge to `main` | The same workspaces, without the review-only changes | The approval step (`apply-approval`), then an apply for each. A deleted workspace file: its Terraform state is removed (the workspace is unchanged) |
| `deploy.yml`, every Monday (or Run workflow) | Every workspace | Drift check: plans each, and opens an issue labelled `drift` for each that no longer matches; closes it once clean |

Which workspaces a change concerns:

| Change | Planned (pull request) | Applied (merge) |
| --- | --- | --- |
| `config/workspaces/<name>.yaml` | That workspace | That workspace (a deleted file: its state is removed) |
| `config/defaults/`, `terraform/` (except `terraform/tests/`), `scripts/tf.sh`, `scripts/plan-guard.py`, `scripts/workspaces.py` | Every workspace | Every workspace |
| What the plan comment shows: `scripts/preflight.py`, `scripts/ai-plan-review.py`, `.github/ai/`, `config/setup.yaml`, `deploy.yml` and what it uses | Every workspace | None |
| Anything else: tests, docs, other scripts | None | None |

A change to every workspace applies them all, each in its own job: one that fails does not
stop the others. Fix it in a pull request; or, if a missing prerequisite was fixed, re-run
that job (it refuses if `main` has moved on). Each workspace's applies run one at a time.
Tests and docs never re-apply a workspace: re-applying is not free (a newer runtime, for
example, can restart running clusters).

## How CI signs in

One Entra service principal, for every workspace and for the Terraform state, through GitHub OIDC: no secret is stored in GitHub. It is workspace admin in each workspace this repository manages. Entra matches each GitHub token's subject exactly, and this repository needs only two federated credentials, whatever the number of workspaces.

One credential for plans (`<prefix>:pull_request`) and one for everything run from `main` (`<prefix>:ref:refs/heads/main`): what the app registration needs, and how to set it up, is in [SETUP.md, step 4](SETUP.md#4-the-pipeline-identity).

No job that signs in runs in a GitHub Environment, because that would change its subject to `environment:<name>`. The one environment, `apply-approval`, is the approval step before each workspace's apply: it holds nothing and signs in to nothing.

Onboarding a workspace therefore needs nothing in GitHub settings or Entra: make the service principal workspace admin there (by hand, [SETUP.md](SETUP.md) step 6), add its file, merge.

## Setup

The one-time setup (state storage, the identity and its federated credentials, repository
settings, the Databricks account) is in [SETUP.md](SETUP.md), steps 3 to 6, with who does
each step. Everything after it is deployed by a merged pull request.

## Runners and network access

The jobs that run Terraform call the workspace API, so the runner must be able to reach the workspace. GitHub-hosted runners use changing public IP addresses, so they are blocked when the workspace:

- uses Private Link with public access disabled, or
- has an IP access list (the error is `Source IP address ... is blocked by Databricks IP ACL`).

In that case, run these jobs on a runner inside an allowed network and set the repository variable `TERRAFORM_RUNNER` to its `runs-on` value, written as JSON:

```text
"citizen-dev"                                              a single runner label (note the quotes)
["self-hosted", "citizen-dev"]                            several labels
{"group": "my-runner-group", "labels": "linux-4core"}    a runner group, with a label
```

| Runner | Notes |
| --- | --- |
| Self-hosted runner in the Azure network (VM or container) | Register it to the repository or organization with a label such as `citizen-dev`, then set `TERRAFORM_RUNNER` to `"citizen-dev"`. Needs `bash`, `python3`, `git`, `node` (for `actions/github-script`), `curl`, `tar` and `sha256sum`, and the **Azure CLI** (the retire job). The jobs install Terraform and the Databricks CLI themselves. Outbound access to: GitHub (github.com, api.github.com, the Actions endpoints), the Terraform registry and releases (registry.terraform.io, releases.hashicorp.com, or your mirror), Entra ID (login.microsoftonline.com), the state storage account (`<account>.blob.core.windows.net`), the Databricks account console (accounts.azuredatabricks.net) and each workspace. |
| GitHub-hosted runners with Azure private networking | GitHub Team or Enterprise; runners join an Azure VNet you provide. Set `TERRAFORM_RUNNER` to the runner group, for example `{"group": "my-runner-group", "labels": "linux-4core"}`. |

The jobs that reach Databricks or the state use `TERRAFORM_RUNNER`. The checks and the routing step use `CHECKS_RUNNER` (default `ubuntu-latest`): set it too if your organization has no GitHub-hosted runners. They run a pull request's code before review, so in a public repository never point `CHECKS_RUNNER` at a self-hosted runner: a pull request from a fork would run on it.

## Hardening and noise

- **Permissions per job.** The workflow grants nothing; each job asks for what it uses: `id-token: write` only where it signs in (plan, apply, retire, drift), `pull-requests: write` only for the plan and retire comments, `issues: write` only for the drift issue.
- **Pinned actions.** Every third-party action is pinned to a commit SHA, with its version in a comment; Dependabot (`.github/dependabot.yml`) proposes updates once a month, as one pull request. `scripts/tests/test_workflows.py` fails on an unpinned action, a job without its own permissions or time limit, or a plan that takes the state lock.
- **No token left in the checkout** (`persist-credentials: false`), except in the apply job, which asks the remote whether `main` moved on before a re-run.
- **Time limits** on every job, so a hung self-hosted runner does not hold a workspace's apply for hours.
- **Plans do not lock the state** (`-lock=false`: a plan never writes it), so a plan never fails because an apply is running. A newer push to a pull request cancels its older plans and checks.
- **The approval label is checked twice.** On the pull request, the plan check fails until a person adds `allow-risky-changes`. At apply, a flagged change goes ahead only if the merged pull request carries the label, so merging past a failed plan check does not apply it. Branch protection cannot require the per-workspace plan jobs (their names change with the workspaces), so the apply-time check is what enforces it on every GitHub plan.
- **Adding or removing `allow-risky-changes` re-runs the plan check**, so the approval takes effect without a new push. Other labels do not re-run anything.
- **Pull requests from forks are not planned:** GitHub gives them no OIDC token, so the plan could only fail.
- **Plan comments** appear only for a plan that changes something, failed, or hit a preflight error. Preflight warnings alone (a placeholder still in the baseline, say) are shown with the next plan that changes something, and in the job's annotations, instead of a new comment on every pull request.
- **Drift issues** get a new comment only when the drift changed; the same drift found again next Monday does not notify anyone again. The issue closes itself when the drift is gone.

## The plan comment

Each affected workspace gets one comment on the pull request, updated on every push, written to be read in about 30 seconds. The plan guard decides what needs approval; the AI review only explains.

| Section | Source | Notes |
| --- | --- | --- |
| Title | Plan | Number of resource changes |
| Preflight | `scripts/preflight.py` | When it found a problem: what is missing, and what to do |
| Risk summary, What does this mean?, What's changing?, What should you review? | `scripts/ai-plan-review.py` | When `ai_review_host` is set. Adapts to the risk: a Low change gets the summary and the table only. It never mentions the approval label or resource addresses |
| Before merging | `scripts/plan-guard.py` (its status) | Only when the plan guard flagged something: approval is needed, and what the `allow-risky-changes` label means. Never written by the AI |
| Technical details | Plan guard, [tf-summarize](https://github.com/dineshba/tf-summarize), plan | Collapsed: the guard's findings with resource addresses, every changed resource, the full plan (its start cut if the comment would exceed GitHub's size limit) |
| Footer | | *AI-generated review based on the Terraform plan. Verify findings before merging.* (only with an AI review) |

The AI review is one call to a model in **one review workspace** (`ai_review_host` in `config/setup.yaml`: any workspace the pipeline's service principal is in, whether or not this repository manages it), whatever workspace the plan is for, signed in as the pipeline. Only that workspace needs the model: `ai_review_model`, by default the Unity Gateway model service `system.ai.claude-sonnet-5-5` (the pipeline identity needs EXECUTE on it; account users have it on `system.ai` by default). It sees the pull request's configuration diff, the diff of the Terraform code and CHANGELOG (so a framework change that changes what is deployed is explained, not reported as drift), the planned changes and the plan guard output, nothing else, and takes seconds. The instructions it follows are `.github/ai/plan-review-prompt.md`.

The review also reads preflight's findings (what it found clean is evidence too), and judges the risk by what could break, who could lose access and whether it can be undone. To change the prompt, run the evaluation cases first and after: `python3 scripts/ai-review-eval.py` ([.github/ai/eval/README.md](../.github/ai/eval/README.md)).

The review is advice only: it never fails the check, and if the model is unavailable the section is left out. With Enforce Unity Gateway on, the `databricks-` serving endpoints are switched off, so use a `system.ai` model service. A change to `config/setup.yaml` or the prompt re-plans every workspace on its pull request, so the comment shows the new review.

## Who can run code with the workspace credentials

The plan job runs on every pull request, with the pull request's own code (the Terraform, the scripts and even the workflow file), and with the pipeline's credentials: the same workspace-admin identity apply uses. Plan cannot use a weaker identity, because reading most workspace settings needs workspace admin. So, by default, **anyone who can push a branch can act as workspace admin on every CI workspace, before anyone reviews the code.** A check inside the workflow cannot stop this, since the pull request can change the workflow; only GitHub's server-side controls can.

Set up all of these before the repository manages real workspaces:

| Control | Where | What it does |
| --- | --- | --- |
| Limit write access | Repository or organization settings | Only the platform team can push branches, so only they can start a plan |
| Code owners | `.github/CODEOWNERS` (replace the owners with your teams), plus a branch protection rule or ruleset on `main`: require a pull request, one approval, and review from code owners | Changes to `terraform/`, `scripts/`, `.github/` and `config/defaults/` need the platform team (and security for `config/defaults/settings.yaml`) before they merge, so before they apply |

The pull request credential cannot be limited to `main`, because plans run from pull request branches; pull requests from forks get no OIDC token at all, so they cannot sign in. The controls above are what keep pull request code from running with the workspace credentials unreviewed: only the platform team can push branches, and code owners review everything outside `config/`.

Required reviewers on environments, branch protection and rulesets need GitHub Team or Enterprise for private repositories.

> [!NOTE]
> A local plan run by a different identity from the one that created a resource can show its permissions as changing: the creator's owner entry. Judge permissions drift from CI plans and the drift check, which run as the pipeline identity.

> [!TIP]
> Local runs (`./scripts/tf.sh`) and CI runs use the same script. In CI it ignores the CLI profiles in the workspace's file (`auth:`), never prompts, and requires `config/backend.hcl`.
