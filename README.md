# Citizen Development Workspace Baseline

A framework for keeping **existing Azure Databricks citizen development workspaces** consistent, secure, and easy to manage: a **Terraform baseline** for every workspace, and an optional **self-service app** where people ask for what they need.

The goal is to make workspace configuration predictable without having to manage each workspace separately. Most changes happen in YAML, go through a pull request, and are deployed by GitHub Actions.

> **New to the project?** Start with [the setup guide](docs/SETUP.md). It walks through the initial setup and onboarding your first workspace.

## What this project manages

Every onboarded workspace gets the same baseline, with workspace-specific settings where needed.

| Area | What's included |
| --- | --- |
| **Security** | Standard workspace admin settings, including restrictions on legacy access, DBFS (root, mounts and the file browser), personal access tokens, Git providers, and other workspace features. Downloads and exports stay allowed by default; each is one setting. User isolation is enforced, and integrations such as Unity Gateway and Microsoft Teams are configured through the baseline. |
| **Access** | Three group-based personas: **Explorer** for SQL access, and **Builder** and **Publisher** for broader workspace access. Members of the workspace's users group get **Consumer** access through Databricks One (the simplified interface for business users: dashboards, Genie spaces and apps). Group membership is managed in Entra ID, not in this repository. |
| **Compute** | A serverless-first setup with a default serverless SQL warehouse and the workspace's serverless usage policy, which tags serverless usage. Classic compute policies for interactive clusters, jobs, and pipelines exist too, each allowing one cluster per user at a time; nobody uses them until a platform admin grants them. |
| **Unity Catalog** | One catalog per workspace with predictive optimization enabled. The self-service app manages schemas within that catalog. |
| **Cost tracking** | A shared set of chargeback tags, defined in `config/defaults/cost.yaml`, applied to serverless usage, the SQL warehouse, and classic compute. |

**This project does not create Databricks workspaces.** It applies and maintains the baseline on workspaces that already exist.

**The self-service app is in this repository too** (`apps/`, deployed by Databricks Asset Bundles from `bundle/`, after Terraform, in the same workflow). People open one web app in a central **hub** workspace, choose their business unit (a workspace, by its prefix), and ask for a personal, project or team schema or a workspace folder; two jobs in their workspace do the work, and platform admins approve what needs it in an approvals app. Without it, workspace admins do those by hand: the baseline works either way ([setup, step 12](docs/SETUP.md#12-the-self-service-app); [design](docs/design.md), section 9).

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
| 2 | Put this project in your GitHub repository, with your teams in `.github/CODEOWNERS`: clone it into a Databricks Git folder and run the `install/copy_to_your_repo` notebook, which copies it into your repository's Git folder without this repository's own environment ([step 2](docs/SETUP.md#2-put-the-repository-in-your-github)). | Platform team |
| 3 | In the Azure portal, create the Terraform state storage account and container, and write their names into `config/backend.hcl`. | Cloud team |
| 4 | In the Azure portal, create the deployment identity: an Entra app registration with two GitHub federated credentials and no secrets ([what it needs](docs/SETUP.md#what-the-app-registration-needs)). | Entra admin |
| 5 | In the GitHub web UI, set the repository variables, labels, the `apply-approval` environment and the protection of `main`. | GitHub admin |
| 6 | In the Databricks account console, add the deployment service principal, grant it workspace admin access to the target workspaces, and give it the **Billing admin** role so it can create serverless usage policies. A metastore admin grants it `CREATE CATALOG` ([step 6](docs/SETUP.md#6-databricks-account-by-hand)). | Databricks account and metastore admins |
| 7 | Create the persona groups in Entra ID and sync them to the Databricks account. | Identity team |
| 8 | Review the baseline YAML files in `config/defaults/` with the platform and security teams, and set the Databricks `account_id` in `config/defaults/cost.yaml`. | Platform and security teams |
| 9 | Copy [`config/workspaces/_example.yaml`](config/workspaces/_example.yaml) to `config/workspaces/<name>.yaml`, update the workspace details, and open a pull request. Read its plan comment before merging; a brand-new workspace first needs one personal access token created and revoked ([step 9](docs/SETUP.md#9-onboard-a-workspace)). | Platform team |

Optionally, **install the self-service app** ([step 12](docs/SETUP.md#12-the-self-service-app)): two pull requests, deployed by the same workflow.

**Every step is done in a web UI** (Databricks, the Azure portal, GitHub, the Databricks account console): nothing needs a terminal or Python on a laptop. With one (the Databricks web terminal works), `scripts/setup.py` can do steps 3 to 5 for you. Follow the setup guide for prerequisites and the full sequence.

## Making changes after setup

Most day-to-day requests fit into one of these paths:

| You want to… | Where to make the change |
| --- | --- |
| Update the baseline for all workspaces | `config/defaults/` |
| Onboard a workspace | Add a YAML file under `config/workspaces/` using `_example.yaml` |
| Change settings for one workspace | Update its file in `config/workspaces/` |
| Change who has Explorer, Builder, or Publisher access | Update group membership in Entra ID (for example, through access packages) |
| Give someone access to classic compute | A platform admin grants the cluster policy (a self-service request for it is not built yet) |
| Change what the self-service app offers, who approves, or its jobs' rights | `config/self-service/app.yaml` |
| Change the app's links, onboarding prompt or banner | The approvals app's **Settings** tab (no pull request) |
| Change who must review configuration changes | `.github/CODEOWNERS` |

Changes to the Terraform modules, scripts, or workflows are **framework changes**, not normal workspace configuration changes. See [AGENTS.md](AGENTS.md) before working on those areas.

## Repository structure

| Path | Purpose |
| --- | --- |
| `config/setup.yaml` | Shared values used during initial setup, including the workspace used for AI plan review. |
| `config/defaults/` | Baseline configuration for access, compute, cost, catalogs, workspace settings, and `genie-code/`. |
| `config/workspaces/` | One YAML file per managed workspace. These files define which workspaces are in scope. |
| `config/backend.hcl` | Terraform state backend configuration, generated by the setup process. |
| `config/self-service/` | The self-service app's configuration: `hub.yaml` (the hub workspace, the apps' identities) and `app.yaml` (what it offers and how). |
| `terraform/` | Root Terraform configuration and reusable modules. |
| `apps/self-service/` | The self-service app and the approvals app (one codebase), and their database migrations. |
| `bundle/` | The Databricks Asset Bundles that deploy them: `hub/` (the apps, the database) and `jobs/` (the two jobs in each workspace). |
| `scripts/` | Setup, workspace onboarding and validation, preflight checks, Terraform execution, plan review, and tests. |
| `.github/` | GitHub Actions workflows (`deploy.yml` and `checks.yml`), `CODEOWNERS`, and the pull request checklist. |
| `docs/` | Setup, design decisions, workflows, and operational guides. |
| `install/` | `copy_to_your_repo`: a Databricks notebook (or one command in the web terminal) that installs or upgrades this project in your repository's Git folder, without this repository's own environment and without replacing your configuration. |
| `dev/` | The framework repository's own notes and test workspaces; never copied into your repository. |
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

For framework maintainers (your repository runs them as the **Tests** check on every pull request). From the repository root:

```bash
./scripts/test.sh
```

The tests run locally without Databricks workspace access or cloud credentials. Terraform tests use mocked providers; the first run downloads the Databricks provider from the Terraform registry (or your mirror). The same suite runs as the **Tests** check on pull requests.

## Support and ownership

Once installed, **your platform team owns this repository**: its configuration, its workflows and who approves changes (`.github/CODEOWNERS`). Configuration questions and workspace changes stay with that team. A problem in the framework itself (Terraform modules, scripts, workflows) goes to the framework's maintainers, so the fix arrives in the next release; see [AGENTS.md](AGENTS.md) before changing those files.
