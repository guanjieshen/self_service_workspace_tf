# Citizen Development Workspace Baseline (Terraform)

## Overview

This project applies one governed baseline to every **existing** Azure Databricks citizen development workspace, and keeps it there. You configure it with YAML only, in pull requests; GitHub Actions plans and applies it.

Each workspace gets:

- **Secure admin settings:** legacy access and DBFS off, user isolation, token limits, downloads, Unity Gateway, Microsoft Teams only, and more.
- **Three personas granted to groups:** explorer (SQL), builder and publisher (full workspace); everyone else gets Consumer access (Databricks One). Who is in each group is managed in Entra ID, for example through access packages.
- **Serverless first:** a default serverless SQL warehouse and one serverless usage policy every persona can use; classic cluster policies (interactive, jobs, pipelines; one cluster each per person) for people the self-service app approves.
- **One Unity Catalog catalog** with predictive optimization; its schemas come from the self-service app.
- **Chargeback tags** from one list (`config/defaults/cost.yaml`), on the usage policy, the warehouse and every classic cluster.

## Get started

> [!IMPORTANT]
> **New here? Follow [docs/SETUP.md](docs/SETUP.md).** It goes from this zip to your first governed workspace, one team at a time. The first thing you edit is **[`config/setup.yaml`](config/setup.yaml)**: the values every setup step reads (your tenant, the state storage, this repository, the Databricks account).

| Step | What | Who |
| --- | --- | --- |
| 1 | Fill in `config/setup.yaml` | Platform team |
| 2 | Push this repository to your GitHub | Platform team |
| 3 to 5 | `python3 scripts/setup.py state`, `identity`, `github` (each prints what it will do; `--run` does it) | Cloud team, Entra admin, GitHub admin |
| 6 | In the Databricks account console, by hand: add the service principal, make it workspace admin, let it create serverless usage (budget) policies | Databricks account admin |
| 7 | Create the Entra groups and sync them to the account | Identity team |
| 8 | Decide the baseline in `config/defaults/` | Platform team, security |
| 9 | Onboard a workspace: copy `config/workspaces/_example.yaml` to `<name>.yaml`, fill it in, open a pull request | Platform team |

## Documentation

| Read | For |
| --- | --- |
| [docs/SETUP.md](docs/SETUP.md) | Setting it up, onboarding workspaces, day to day, upgrades, troubleshooting |
| [docs/user-journeys.md](docs/user-journeys.md) | Step by step: add a workspace, change one or all, give access, retire one |
| [config/README.md](config/README.md) | Changing the configuration: which key to set for what |
| [docs/design.md](docs/design.md) | Why it works the way it does |
| [docs/github-actions.md](docs/github-actions.md) | The plan, apply and drift workflows |
| [CHANGELOG.md](CHANGELOG.md) | What changed in each release |
| [AGENTS.md](AGENTS.md) | Changing the project itself (for coding agents and maintainers) |

## Layout

| Path | What it is |
| --- | --- |
| `config/defaults/` | The baseline every workspace gets: `access`, `compute`, `cost`, `catalog`, `settings` `.yaml`, `genie-code/` |
| `config/workspaces/<name>.yaml` | One file per workspace: `bu`, `host`, its groups, and any change to the baseline. The files are the list of workspaces |
| `config/setup.yaml` | The setup values ([docs/SETUP.md](docs/SETUP.md), step 1), and which workspace's model reviews plans |
| `config/backend.hcl`, `.github/CODEOWNERS` | Where state is kept (written by `setup.py state`), who approves what |
| `terraform/` | The root module and modules. You do not edit these for normal operations |
| `scripts/` | `setup.py` (one-time setup), `workspaces.py` (new workspace, which workspaces a change affects, checks), `preflight.py` (is a workspace ready?), `tf.sh` (run Terraform), `plan-guard.py`, `ai-plan-review.py`, `test.sh` |
| `.github/` | `deploy.yml` (plan, apply and drift, one job per workspace) and `checks.yml` (pull request checks) ([docs/github-actions.md](docs/github-actions.md)) |
| `docs/` | Setup, design and CI documentation |
| `dev/` | The framework's own test workspaces; not in a release |
| `AGENTS.md`, `agents/` | Guidance for coding agents: `AGENTS.md` is the entry point (`CLAUDE.md` points Claude Code to it), `agents/` has one guide per area |

Everything outside `config/` (and `.github/CODEOWNERS`) is the framework: you upgrade it, you do not edit it.

## Tests

```bash
./scripts/test.sh
```

Runs every test without a workspace or credentials (Terraform against mocked providers), the same as the **Tests** check on every pull request.
