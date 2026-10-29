# Automated deployment with GitHub Actions

## Overview

**One workflow per workspace.** Each workspace folder has its own small workflow,
`.github/workflows/workspace-<name>.yml`, which only names the workspace and the paths that
concern it; all the steps are in the shared `.github/workflows/workspace.yml`. `scripts/workspaces.py new`
writes a new workspace's workflow, and `workspaces.py check` (in **Format and validate**)
fails if a folder has no workflow, a workflow has no folder, or a workflow differs from the
template (`workspaces.py workflows` rewrites them all).

| Workflow | Runs on | Does |
| --- | --- | --- |
| `checks.yml` (**Format and validate**, **Tests**) | Every pull request | Formatting, `terraform validate`, the cross-workspace checks, every test. Required by branch protection |
| `workspace-<name>.yml`, on a pull request | A change that concerns the workspace (below) | Preflight, plan, and the plan comment: the plan, the plan guard's warnings, an AI review. A plan with hard-to-undo or security-weakening changes fails until someone adds the label `allow-risky-changes` |
| `workspace-<name>.yml`, on merge to `main` | The same changes, without the review-only ones | The approval step (`apply-approval`), then apply |
| `workspace-<name>.yml`, every Monday (or Run workflow) | Schedule | Drift check: plans, and opens an issue labelled `drift` if the live settings no longer match; closes it once clean |

Which changes concern a workspace:

| Change | Planned (pull request) | Applied (merge) |
| --- | --- | --- |
| `config/workspaces/<name>/` | That workspace | That workspace |
| `config/defaults/`, `terraform/` (except `terraform/tests/`), `scripts/tf.sh`, `scripts/plan-guard.py` | Every workspace | Every workspace |
| What the plan comment shows: `scripts/preflight.py`, `scripts/ai-plan-review.py`, `.github/ai/`, `config/setup.yaml`, the workflows | Every workspace | None |
| Anything else: tests, docs, other scripts | None | None |

A change to every workspace applies them all at the same time, each in its own workflow:
one that fails does not stop the others. Fix it in a pull request; or, if a missing
prerequisite was fixed, re-run that workspace's latest run (it refuses if `main` has moved
on). Each workspace's applies run one at a time. Tests and docs never re-apply a workspace:
re-applying is not free (a newer runtime, for example, restarts the shared cluster).

## How CI signs in

One Entra service principal, for every workspace and for the Terraform state, through GitHub OIDC: no secret is stored in GitHub. It is workspace admin in each workspace this repository manages. Entra matches each GitHub token's subject exactly, and this repository needs only two federated credentials, whatever the number of workspaces:

| Credential | Subject | Used by |
| --- | --- | --- |
| `github-pull-requests` | `<prefix>:pull_request` | Plans (every pull request) |
| `github-main` | `<prefix>:ref:refs/heads/main` | Applies (merge to `main`), drift checks (scheduled, or run on `main`) |

`<prefix>` is the repository's, for example `repo:my-org@123456/my-repo@456789` (repositories created or renamed since July 15, 2026 include numeric IDs): `gh api repos/<org>/<repo>/actions/oidc/customization/sub --jq .sub_claim_prefix`. `scripts/setup.py identity` reads it and creates both credentials.

No job that signs in runs in a GitHub Environment, because that would change its subject to `environment:<name>`. The one environment, `apply-approval`, is the approval step before each workspace's apply: it holds nothing and signs in to nothing.

Onboarding a workspace therefore needs nothing in GitHub settings or Entra: make the service principal workspace admin there (by hand, [SETUP.md](SETUP.md) step 6), add the folder and its workflow (`workspaces.py new` writes both), merge.

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
| Self-hosted runner in the Azure network (VM or container) | Register it to the repository or organization with a label such as `citizen-dev`, then set `TERRAFORM_RUNNER` to `"citizen-dev"`. Needs `bash`, `python3`, `git` and outbound access to GitHub and the workspace. |
| GitHub-hosted runners with Azure private networking | GitHub Team or Enterprise; runners join an Azure VNet you provide. Set `TERRAFORM_RUNNER` to the runner group, for example `{"group": "my-runner-group", "labels": "linux-4core"}`. |

Only the jobs that reach Databricks use `TERRAFORM_RUNNER`; format checks and workspace detection stay on `ubuntu-latest`.

## The plan comment

Each affected workspace gets one comment on the pull request, updated on every push:

| Section | Source | Notes |
| --- | --- | --- |
| Title | Plan | Number of resource changes |
| Preflight | `scripts/preflight.py` | Only when it found a problem: what is missing, and what to do |
| Warning | `scripts/plan-guard.py` | Only when the plan has hard-to-undo changes |
| AI impact review | `scripts/ai-plan-review.py` | When `ai_review_workspace` is set in `config/setup.yaml`. Risk level, a plain-language table of changes and who they affect, and up to three things to check |
| Changed resources | [tf-summarize](https://github.com/dineshba/tf-summarize) | Table of every resource added, changed or removed (collapsed) |
| Full Terraform plan | Plan | Collapsed; the start is cut if the comment would exceed GitHub's size limit |

The AI review is one call to a model in **one review workspace** (`ai_review_workspace` in `config/setup.yaml`, a workspace folder this repository manages), whatever workspace the plan is for, signed in as the pipeline. Only that workspace needs the model: `ai_review_model`, by default the Unity Gateway model service `system.ai.claude-sonnet-5-5` (the pipeline identity needs EXECUTE on it; account users have it on `system.ai` by default). It sees the pull request's configuration diff, the planned changes and the plan guard output, nothing else, and takes seconds. The instructions it follows are `.github/ai/plan-review-prompt.md`.

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
> Local runs (`./scripts/tf.sh`) and CI runs use the same script. In CI it ignores the CLI profiles in `workspace.yaml`, never prompts, and requires `config/backend.hcl`.
