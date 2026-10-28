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

## One-time setup

### 1. Terraform state storage

1. Create an Azure Storage account and a container for state (for example `tfstate`), with public access disabled.
2. Copy `config/backend.hcl.example` to `config/backend.hcl`, fill in the names, and commit it. It contains no secrets. Each workspace gets its own state file, `citizen-dev/<name>.tfstate`.

### 2. Automation identities

CI signs in with one Entra service principal through GitHub OIDC, for both the Terraform state (Azure Storage) and Databricks. No secret is stored in GitHub.

#### 2a. GitHub OIDC subjects

Entra federated credentials match the token's subject exactly. Repositories created or renamed on or after July 15, 2026 use subjects that include numeric IDs. Get this repository's prefix with:

```bash
gh api repos/<org>/<repo>/actions/oidc/customization/sub --jq .sub_claim_prefix
# for example: repo:my-org@123456/my-repo@456789
```

Every job that signs in runs in the workspace's environment, so there is one subject per workspace, used by plan, drift and apply:

```text
<prefix>:environment:workspace-<name>
```

#### 2b. Entra service principal

1. Create an Entra app registration and service principal, for example `sp-citizen-dev-terraform`.
2. Add a **federated credential** for each subject in 2a (Certificates & secrets > Federated credentials > Other issuer). Issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`.
3. Give it **Storage Blob Data Contributor** on the state container.
4. Give it the Databricks rights in 2c.

#### 2c. Databricks rights

| Where | Permission |
| --- | --- |
| Databricks account | Add the service principal; give it the permission to create budget policies |
| Each workspace | Assign the service principal and make it workspace admin |

### 2d. Network access to the workspace

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

### 3. Repository settings

1. **Variables** (Settings > Secrets and variables > Actions > Variables). These are identifiers, not secrets:

   | Variable | When |
   | --- | --- |
   | `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | Always |
   | `TERRAFORM_RUNNER` | Optional; JSON `runs-on` value for jobs that reach the workspace (2d), `"ubuntu-latest"` when unset |

2. **Environments** (Settings > Environments): two per workspace.

   | Environment | Holds | Protection | Used by |
   | --- | --- | --- | --- |
   | `workspace-<name>` | Nothing (it is the subject of the federated credential, 2a) | None | Plan, drift and apply jobs |
   | `workspace-<name>-approval` | Nothing | **Required reviewers**; deployment branch `main` | The approval step before apply |

   Required reviewers need a GitHub plan that supports them for private repositories (Team or Enterprise for organizations). Until they are added, merging the pull request is the only approval: the apply runs straight after the merge. GitHub also creates a missing environment automatically, without reviewers, so check each new `workspace-<name>-approval` environment has them.
3. **Labels:** create `allow-risky-changes` and `drift`.
4. **Branch protection** on `main`: require pull requests and the `Plan` checks to pass, including **Tests** (the plans wait for it, so a pull request that breaks a test gets no plan).
   This is what stops a pull request being merged before its plan, plan guard and AI review have finished; without it, GitHub allows the merge while checks are still running, and the apply runs on a change nobody saw a plan for.
   Like required reviewers, it needs a GitHub plan that supports it for private repositories. Without it, wait until every check on the pull request has finished before merging.

## What GitHub Actions does not do

With the setup above done and the configuration right, a merged pull request deploys
everything else: workspace settings, groups and entitlements, catalogs, schemas and grants,
the on-request jobs and their notebooks, and compute.
These steps stay outside it, because they create the identity or the storage Actions itself
needs, need more than workspace admin, or are a person's decision by design:

| Step | Who | When | Why not in Actions |
| --- | --- | --- | --- |
| State storage account and `config/backend.hcl` (1) | Cloud team | Once | Terraform's own state lives there |
| Entra service principal, its role on the state, federated credentials (2a, 2b) | Entra admin | Once; one credential per new workspace | It is the identity Actions signs in as |
| Add the service principal to the Databricks account, with the budget policy permission (2c) | Databricks account admin | Once | Needs account admin; giving CI account admin is too broad |
| Make the service principal workspace admin (2c) | Account or workspace admin | Per new workspace | The same: it is how CI gets in |
| The workspace itself, with Unity Catalog | Your provisioning process | Per new workspace | This repository configures workspaces; it does not create them |
| Entra groups synced to the account (`{bu}_users`, `{bu}_explorer`, `{bu}_builder`, `{bu}_publisher`, `{bu}_platform_admins`) | Identity team | Per business unit | Entra owns people and groups |
| Repository variables, labels, environments with reviewers, branch protection, CODEOWNERS (3) | GitHub organization admin | Once; two environments per new workspace (`scripts/workspaces.py new` prints the commands) | Repository administration, not deployment |
| A runner inside the network, if workspaces use Private Link or IP access lists (2d) | Cloud team | Once | Infrastructure Actions runs on |
| `restrict_workspace_admins: true` | Only with an account admin running Terraform | If wanted | Needs account admin; leave it `false` otherwise |
| Approve a deployment, add `allow-risky-changes`, act on a `drift` issue | Reviewers | Per change | A person decides, by design |

## The plan comment

Each affected workspace gets one comment on the pull request, updated on every push:

| Section | Source | Notes |
| --- | --- | --- |
| Title | Plan | Number of resource changes |
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

## Day to day

| Task | How |
| --- | --- |
| Change a workspace | PR editing files in `config/workspaces/<name>/`; review the plan comment; merge; approve the deployment |
| Change the baseline | PR editing `config/defaults/`; the PR shows a plan for every workspace |
| Onboard a workspace | Run `scripts/workspaces.py new`, open a PR with the new folder, create its two environments (the script prints the commands), the federated credential or federation policy for its subject, then set `ci: true` |
| Test a workspace's credentials | Set `ci: true` and open a pull request that touches the workspace: its plan signs in with them (and changes nothing) |
| Re-apply one workspace | Actions > Apply > Run workflow, enter the workspace name |
| Investigate drift | Open the `drift` issue; either update the configuration or re-apply |

## Who can run code with the workspace credentials

The plan job runs on every pull request, with the pull request's own code (the Terraform, the scripts and even the workflow file), and with the workspace's credentials: the same workspace-admin identity apply uses. Plan cannot use a weaker identity, because reading most workspace settings needs workspace admin. So, by default, **anyone who can push a branch can act as workspace admin on every CI workspace, before anyone reviews the code.** A check inside the workflow cannot stop this, since the pull request can change the workflow; only GitHub's server-side controls can.

Set up all of these before the repository manages real workspaces:

| Control | Where | What it does |
| --- | --- | --- |
| Limit write access | Repository or organization settings | Only the platform team can push branches, so only they can start a plan |
| Code owners | `.github/CODEOWNERS` (replace the owners with your teams), plus a branch protection rule or ruleset on `main`: require a pull request, one approval, and review from code owners | Changes to `terraform/`, `scripts/`, `.github/` and `config/defaults/` need the platform team (and security for `config/defaults/settings.yaml`) before they merge, so before they apply |

Plans and applies share the `workspace-<name>` environment, so it cannot be limited to `main` (plans run from pull request branches). The controls above are what keep pull request code from running with the workspace credentials unreviewed: only the platform team can push branches, and code owners review everything outside `config/`.

Required reviewers on environments, branch protection and rulesets need GitHub Team or Enterprise for private repositories (this test repository has none of them, so it runs without these controls).

> [!NOTE]
> A local plan run by a different identity from the one that created a resource can show its permissions as changing: the creator's owner entry. Judge permissions drift from CI plans and the drift check, which run as the pipeline identity.

> [!TIP]
> Local runs (`./scripts/tf.sh`) and CI runs use the same script. In CI it ignores the CLI profiles in `workspace.yaml`, never prompts, and requires `config/backend.hcl`.
