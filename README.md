# Citizen Development Workspace Baseline

A Terraform framework for keeping **existing Azure Databricks citizen development workspaces** consistent, secure, and easy to manage.

The goal is to make workspace configuration predictable without having to manage each workspace separately. Most changes happen in YAML, go through a pull request, and are deployed by GitHub Actions.

> **New to the project?** Start with [the setup guide](docs/SETUP.md). It walks through the initial setup and onboarding your first workspace.

## What this project manages

Every onboarded workspace gets the same baseline, with workspace-specific settings where needed.

| Area | What's included |
| --- | --- |
| **Security** | Standard workspace admin settings, including restrictions on legacy access, DBFS, downloads, personal access tokens, Git providers, and other workspace features. User isolation is enforced, and integrations such as Unity Gateway and Microsoft Teams are configured through the baseline. |
| **Access** | Three group-based personas: **Explorer** for SQL access, and **Builder** and **Publisher** for broader workspace access. Members of the workspace's users group get **Consumer** access through Databricks One (the simplified interface for business users: dashboards, Genie spaces and apps). Group membership is managed in Entra ID, not in this repository. |
| **Compute** | A serverless-first setup with a default serverless SQL warehouse and the workspace's serverless usage policy, which tags serverless usage. Approved users can also request access to classic compute policies for interactive clusters, jobs, and pipelines through the self-service app. Each classic policy allows one cluster per user at a time. |
| **Unity Catalog** | One catalog per workspace with predictive optimization enabled. The self-service app manages schemas within that catalog. |
| **Cost tracking** | A shared set of chargeback tags, defined in `config/defaults/cost.yaml`, applied to serverless usage, the SQL warehouse, and classic compute. |

**This project does not create Databricks workspaces.** It applies and maintains the baseline on workspaces that already exist.

**The self-service app is a separate project**, not included here. It handles what people request: schemas, team folders, project usage policies, and access to classic compute. Without it, workspace admins do those by hand; this baseline works either way.

## How it works

There are two main layers of configuration:

- **`config/defaults/`** defines the baseline shared by all workspaces.
- **`config/workspaces/`** lists the workspaces managed by this project and holds their workspace-specific values and overrides.

When you open a pull request, the GitHub workflows run checks and generate Terraform plans so you can review the impact before changes are applied. The deployment workflows also support drift detection to flag changes made outside the repository.

For normal operations, you should not need to edit Terraform modules or deployment scripts. Start with the YAML configuration.

## Getting started

The full walkthrough is in [docs/SETUP.md](docs/SETUP.md). Here's the setup process at a glance:

| Step | What to do | Usually handled by |
| --- | --- | --- |
| 1 | Fill in [`config/setup.yaml`](config/setup.yaml) with the Azure tenant, Terraform state storage, and GitHub repository details. | Platform team |
| 2 | Push this project to your GitHub repository, with your teams in `.github/CODEOWNERS`. | Platform team |
| 3 | Run `python3 scripts/setup.py state` to prepare Terraform state storage and its backend configuration. | Cloud team |
| 4 | Run `python3 scripts/setup.py identity` to prepare the deployment identity: an Entra app registration with two GitHub federated credentials and no secrets ([what it needs](docs/SETUP.md#what-the-app-registration-needs)). | Entra admin |
| 5 | Run `python3 scripts/setup.py github` to configure GitHub for deployments. | GitHub admin |
| 6 | In the Databricks account console, add the deployment service principal, grant it workspace admin access to the target workspaces, and give it the **Billing admin** role so it can create serverless usage policies. A metastore admin grants it `CREATE CATALOG` ([step 6](docs/SETUP.md#6-databricks-account-by-hand)). | Databricks account and metastore admins |
| 7 | Create the persona groups in Entra ID and sync them to the Databricks account. | Identity team |
| 8 | Review the baseline YAML files in `config/defaults/` with the platform and security teams, and set the Databricks `account_id` in `config/defaults/cost.yaml`. | Platform and security teams |
| 9 | Copy [`config/workspaces/_example.yaml`](config/workspaces/_example.yaml) to `config/workspaces/<name>.yaml`, update the workspace details, and open a pull request. Its first plan needs the `allow-risky-changes` label; a brand-new workspace first needs one personal access token created and revoked ([step 9](docs/SETUP.md#9-onboard-a-workspace)). | Platform team |

The setup commands in steps 3–5 **show what they would do by default**. Add `--run` when you're ready to execute a step. Follow the setup guide for prerequisites and the full sequence, and for the steps done by hand: some Databricks settings have no API yet (step 9).

## Making changes after setup

Most day-to-day requests fit into one of these paths:

| You want to… | Where to make the change |
| --- | --- |
| Update the baseline for all workspaces | `config/defaults/` |
| Onboard a workspace | Add a YAML file under `config/workspaces/` using `_example.yaml` |
| Change settings for one workspace | Update its file in `config/workspaces/` |
| Change who has Explorer, Builder, or Publisher access | Update group membership in Entra ID (for example, through access packages) |
| Give someone access to classic compute | Use the self-service app's approval process |
| Change who must review configuration changes | `.github/CODEOWNERS` |

Changes to the Terraform modules, scripts, or workflows are **framework changes**, not normal workspace configuration changes. See [AGENTS.md](AGENTS.md) before working on those areas.

## Repository structure

| Path | Purpose |
| --- | --- |
| `config/setup.yaml` | Shared values used during initial setup, including the workspace used for AI plan review. |
| `config/defaults/` | Baseline configuration for access, compute, cost, catalogs, workspace settings, and `genie-code/`. |
| `config/workspaces/` | One YAML file per managed workspace. These files define which workspaces are in scope. |
| `config/backend.hcl` | Terraform state backend configuration, generated by the setup process. |
| `terraform/` | Root Terraform configuration and reusable modules. |
| `scripts/` | Setup, workspace onboarding and validation, preflight checks, Terraform execution, plan review, and tests. |
| `.github/` | GitHub Actions workflows (`deploy.yml` and `checks.yml`), `CODEOWNERS`, and the pull request checklist. |
| `docs/` | Setup, design decisions, workflows, and operational guides. |
| `dev/` | Workspaces used to test the framework itself; not included in a release. |
| `AGENTS.md`, `agents/`, `CLAUDE.md` | Contributor and coding-agent guidance. `AGENTS.md` is the main entry point. |

## Documentation

- **[Setup and operations](docs/SETUP.md)** — Initial setup, workspace onboarding, routine operations, upgrades, and troubleshooting.
- **[Common workflows](docs/user-journeys.md)** — Adding, updating, and retiring workspaces; changing access.
- **[Configuration reference](config/README.md)** — Which YAML file and setting to change.
- **[Design](docs/design.md)** — The architecture and the reasoning behind it.
- **[GitHub Actions](docs/github-actions.md)** — How checks, plans, deployments, and drift detection work.
- **[Installing in your organization's GitHub](docs/github-enterprise.md)** — Moving the project into your own GitHub, including GitHub Enterprise.
- **[Changelog](CHANGELOG.md)** — Changes between releases.
- **[Contributor guidance](AGENTS.md)** — How to work on the framework itself.

## Running tests

From the repository root:

```bash
./scripts/test.sh
```

The tests run locally without Databricks workspace access or cloud credentials. Terraform tests use mocked providers; the first run downloads the Databricks provider from the Terraform registry (or your mirror). The same suite runs as the **Tests** check on pull requests.

## Support and ownership

Once installed, **your platform team owns this repository**: its configuration, its workflows and who approves changes (`.github/CODEOWNERS`). Configuration questions and workspace changes stay with that team. A problem in the framework itself (Terraform modules, scripts, workflows) goes to the framework's maintainers, so the fix arrives in the next release; see [AGENTS.md](AGENTS.md) before changing those files.
