# Automated deployment with GitHub Actions

## Overview

Every change to a workspace goes through a pull request:

1. **Open a PR** that edits a workspace folder or the baseline.
2. **Plan** (`.github/workflows/plan.yml`) checks formatting, works out which workspaces the change affects, plans each one, and posts the plan as a PR comment. If a plan contains hard-to-undo changes (deleted folders, replaced warehouses, disabling legacy access) or weakens security (a security setting turned off or loosened, a catalog opened to every workspace, a grant to `account users`, more groups allowed to create tokens), the check fails until someone adds the label `allow-risky-changes`. Controls newly left unmanaged are listed as releases and do not fail it.
3. **Merge** the PR to `main`.
4. **Apply** (`.github/workflows/apply.yml`) applies each affected workspace after a reviewer approves the deployment in the workspace's approval environment. It rolls out in rings (`ring` in `workspace.yaml`: 0 first, then 1, the default, then 2), one workspace at a time, and stops at the first workspace that fails, so a broken baseline change does not go on to the rest; fix it and re-run. Run it by hand with **plan only** to preview a rollout.
5. **Drift check** (`.github/workflows/drift.yml`) plans every workspace every Monday and opens an issue labelled `drift` for any workspace whose live settings no longer match the configuration. The issue closes itself once the workspace is clean again.

Which workspaces a change affects:

| Change | Planned (pull request) | Applied (merge) |
| --- | --- | --- |
| `config/workspaces/<name>/` | That workspace | That workspace |
| `config/defaults/`, `terraform/` (except `terraform/tests/`), `scripts/tf.sh`, `scripts/plan-guard.py` | Every workspace | Every workspace |
| The AI review: `scripts/ai-*.py`, `.github/ai/` | Every workspace, to show the new review | None |
| Anything else: tests, docs, other scripts | None | None |

Tests and docs never re-apply a workspace. Re-applying is not free: a newer runtime, for example, restarts the shared cluster.

Workspaces with `ci: false` in their `workspace.yaml` (for example a local sandbox) and folders starting with `_` are always skipped.

## How CI signs in

One Entra service principal, for every workspace and for the Terraform state, through GitHub OIDC: no secret is stored in GitHub. It is workspace admin in each workspace this repository manages. Entra matches each GitHub token's subject exactly, and this repository needs only two federated credentials, whatever the number of workspaces:

| Credential | Subject | Used by |
| --- | --- | --- |
| `github-pull-requests` | `<prefix>:pull_request` | Plan (every pull request) |
| `github-main` | `<prefix>:ref:refs/heads/main` | Apply (merge to `main`), Drift (scheduled, or run on `main`) |

`<prefix>` is the repository's, for example `repo:my-org@123456/my-repo@456789` (repositories created or renamed since July 15, 2026 include numeric IDs): `gh api repos/<org>/<repo>/actions/oidc/customization/sub --jq .sub_claim_prefix`. `scripts/setup.py identity` reads it and creates both credentials.

No job that signs in runs in a GitHub Environment, because that would change its subject to `environment:<name>`. The one environment, `apply-approval`, is the approval step before each workspace's apply: it holds nothing and signs in to nothing.

Onboarding a workspace therefore needs nothing in GitHub or Entra: make the service principal workspace admin there (by hand, [SETUP.md](SETUP.md) step 6), add the folder, merge.

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
| AI impact review | `scripts/ai-plan-review.py` | When enabled in `config/ai-review.yaml` (or the workspace's `ai-review.yaml`). Risk level, a plain-language table of changes and who they affect, and up to three things to check |
| Changed resources | [tf-summarize](https://github.com/dineshba/tf-summarize) | Table of every resource added, changed or removed (collapsed) |
| Full Terraform plan | Plan | Collapsed; the start is cut if the comment would exceed GitHub's size limit |

The AI review is one call to a model in the workspace being planned (by default the Unity Gateway model service `system.ai.claude-sonnet-5-5`), with the same sign-in as Terraform. It sees the pull request's configuration diff, the planned changes and the plan guard output, nothing else, and takes seconds. The pipeline identity needs EXECUTE on the model service (account users have it on `system.ai` by default), or Can query on a serving endpoint.

These files control it, so changes go through a pull request:

| File | Controls |
| --- | --- |
| `config/ai-review.yaml` | The default for every workspace: on or off, the model, the answer limit, and the prompt file |
| `config/workspaces/<name>/ai-review.yaml` | Optional overrides for one workspace (`enabled`, `endpoint`, `max_tokens`), because the models available differ by workspace and region. Template in `config/workspaces/_example/`. Not read by Terraform |
| `.github/ai/plan-review-prompt.md` | What the reviewer knows about the repository, what it looks for, and how it formats the answer |

To try a different model or prompt on one pull request, change these files in that pull request: its plan comment uses them. The review is advice only: it never fails the check, and if the model is unavailable the section is left out. With Enforce Unity Gateway on, the `databricks-` serving endpoints are switched off, so use a `system.ai` model service.

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
