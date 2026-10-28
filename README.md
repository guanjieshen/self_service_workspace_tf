# Citizen Development Workspace Baseline (Terraform)

## Overview

This project applies one governed baseline to every **existing** Azure Databricks citizen development workspace, and keeps it there. You configure it with YAML only, in pull requests; GitHub Actions plans and applies it.

Each workspace gets:

- **Secure admin settings:** legacy access and DBFS off, user isolation, token limits, downloads, Git allowlist, Unity Gateway, Microsoft Teams only, and more.
- **Three personas granted to groups:** explorer (SQL), builder and publisher (full workspace); everyone else gets Consumer access (Databricks One). Who is in each group is managed in Entra ID, for example through access packages.
- **Compute people can use straight away:** a default serverless SQL warehouse, a shared classic cluster, and a cluster policy for one personal cluster each.
- **One Unity Catalog catalog** with predictive optimization, data classification and data quality monitoring, and **personal schemas** (`cd_<name>`) created on request by a job.
- **Chargeback:** required tags, a shared serverless usage policy, and team warehouses.
- **On-request jobs** for personal, project and team schemas and team folders, run by workspace admins or by a service principal you allow (a ticketing system, or a self-service app built on top: [docs/future.md](docs/future.md)).

How it works, and why: [DESIGN.md](DESIGN.md). How to change the configuration: [config/README.md](config/README.md).

## Layout

| Path | What it is |
| --- | --- |
| `config/defaults/` | The baseline every workspace gets: `access`, `compute`, `cost`, `catalog`, `settings` `.yaml`, `genie-code/` |
| `config/workspaces/<name>/` | One folder per workspace: `workspace.yaml`, plus the same file names to change the baseline for that workspace |
| `config/ai-review.yaml`, `config/backend.hcl`, `.github/CODEOWNERS` | The AI review's model, where state is kept, who approves what |
| `terraform/` | The root module and modules. You do not edit these for normal operations |
| `scripts/` | `tf.sh` (run Terraform), `workspaces.py` (new workspace, which workspaces a change affects, checks), `plan-guard.py`, `ai-plan-review.py`, `test.sh` |
| `.github/` | Plan, apply and drift workflows ([docs/github-actions.md](docs/github-actions.md)) |
| `dev/` | The framework's own test workspaces; not in a release |
| `AGENTS.md`, `agents/` | Guidance for coding agents: `AGENTS.md` is the entry point (`CLAUDE.md` points Claude Code to it), `agents/` has one guide per area |

Everything outside `config/` (and `.github/CODEOWNERS`) is the framework: you upgrade it, you do not edit it.

## Prerequisites

1. Terraform 1.9 or later, Python 3.9 or later, and the Databricks CLI.
2. The workspace exists and uses Unity Catalog.
3. **The groups exist as account groups** (Entra ID groups synced to the Databricks account): `{bu}_users`, `{bu}_explorer`, `{bu}_builder`, `{bu}_publisher`, `{bu}_platform_admins`. Unity Catalog and usage policies cannot use groups that exist only in a workspace.
4. The identity running Terraform is a workspace admin. Usage policies also need the account-level permission to create them (otherwise set `budget_policies.enabled: false`).

## Onboard a workspace

1. Create its folder:

   ```bash
   python3 scripts/workspaces.py new fin-citizen-dev --bu fin --lob FIN \
     --host https://adb-1234567890123456.7.azuredatabricks.net \
     --account-id <databricks-account-id>
   ```

2. Review the files in `config/workspaces/fin-citizen-dev/`. Most are comments: keep only what this workspace changes from the baseline.
3. Open a pull request, or plan locally: `./scripts/tf.sh fin-citizen-dev plan`.
4. Merge: the Apply workflow deploys it. That is the only way changes reach a workspace; `tf.sh apply` refuses outside GitHub Actions. The next plan should show no changes.

> [!WARNING]
> On an existing workspace, check that nothing uses Hive metastore tables, DBFS mounts or No-isolation clusters before applying: after 30 days with legacy access disabled, the workspace is Unity Catalog only, permanently. If it is not ready, set `disable_legacy_access: null` and `disable_dbfs_root_and_mounts: null` under `settings:` in its `settings.yaml`.

## Tests

```bash
./scripts/test.sh
```

Runs every test without a workspace or credentials (Terraform against mocked providers), the same as the **Tests** check on every pull request.

## Installing and upgrading

Releases are git tags (`v1.2.0`), with what changed in `CHANGELOG.md`.

**Install** a release into your organization's repository:
```bash
git archive --remote=<framework repo> v1.2.0 | tar -x     # or download the tag's source archive
rm -rf dev config/backend.hcl                              # the framework's own test workspaces and state
```

**Upgrade** to a newer release: replace the framework files, keep your configuration.
```bash
git fetch <framework repo> 'refs/tags/*:refs/tags/*'
git restore --source=v1.3.0 --staged --worktree -- \
  terraform scripts .github/workflows .github/actions .github/scripts .github/ai docs \
  README.md DESIGN.md CHANGELOG.md AGENTS.md CLAUDE.md agents config/README.md config/AGENTS.md \
  config/workspaces/_example
```
`git restore` also removes files the release dropped, and touches nothing else: not `config/defaults/`, your workspaces, `config/ai-review.yaml` or `.github/CODEOWNERS`. A baseline setting that is new in the release is absent from your `config/defaults/` until you add it, which means "leave alone", so an upgrade never turns something on by itself; `CHANGELOG.md` lists new settings to add. Open a pull request: its plan shows what the new version changes in each workspace before anything is applied.

> [!WARNING]
> Do not edit framework files in your repository: the next upgrade replaces them. Send a fix to the framework maintainers so it is in the next release.

## State and teardown

State is local (`.state/<name>.tfstate`) unless `config/backend.hcl` exists (copy `config/backend.hcl.example`); then each workspace has its own state file in Azure Storage, which CI requires.

`./scripts/tf.sh <name> destroy` removes what this project manages. It resets the workspace configuration keys it manages (`enable*`, `enforce*`) to `false`, which includes turning personal access tokens off; review the plan before confirming.
