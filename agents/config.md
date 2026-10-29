# Working on config/

Read the repository's [AGENTS.md](../AGENTS.md) first. This folder is the organization's
configuration: in an installed instance it is the only place people (and agents helping
them) change. The full guide is [config/README.md](../config/README.md); this is the short version.

## The rule

A workspace is one file, `config/workspaces/<name>.yaml`. It changes a default by setting
**the same top-level key as the baseline** (every key is defined in exactly one file of
`config/defaults/`), with the same shape.

- Maps merge key by key; a list or a value replaces the default.
- `null` means "Terraform leaves this alone". On a workspace that was already applied,
  the setting is released (it keeps its current value), never reset.
- A key the baseline does not have fails the plan with its name, so a typo cannot
  silently do nothing.
- Keys only a workspace has: `bu`, `host` (required), `genie_code_instructions`, `label`, and rarely `account_id`, `auth`, `id`
  (`workspace_keys` in `terraform/config.tf`).
- Each workspace names its persona groups (`groups:`); a persona left `null` is skipped.
  Only `groups.platform_admins` comes from the baseline.
- `tags` is an open map: a workspace file may change a value, add a tag, or set one to
  `null` to drop it.
- Terraform holds only what every workspace has and rarely changes. What a team or a
  project requests (another warehouse, its own usage policy, access to classic compute)
  belongs to the self-service app: do not add a key for it here.

## Helping someone change the configuration

1. Find the setting in `config/defaults/` (its comment says what it does) and the task in
   `config/README.md` ("Common tasks").
2. For one workspace, set only the keys that differ, in that workspace's file. For every
   workspace, change `config/defaults/` (reviewed more strictly: CODEOWNERS).
3. Open a pull request. Its plan comment shows what changes in each workspace; the AI
   review lists deviations from the baseline. Merging applies it.
4. Never weaken a security setting in `config/defaults/settings.yaml` without saying so in
   the PR: the plan guard flags it and a person must approve with a label.

Do not change files outside `config/` (and `.github/CODEOWNERS`) in an instance: they are
the framework and the next upgrade replaces them.

## Files

| File | What it holds |
| --- | --- |
| `defaults/access.yaml` | Personas and their rights; the platform admins group (each workspace names its persona groups) |
| `defaults/compute.yaml` | The default SQL warehouse and the classic cluster policy |
| `defaults/cost.yaml` | The chargeback tags and the serverless usage policy |
| `defaults/catalog.yaml` | The workspace catalog and its grants |
| `defaults/settings.yaml` | Workspace admin and security settings |
| `defaults/genie-code/` | Genie Code instructions and skills for every workspace |
| `workspaces/<name>.yaml` | One file per workspace (copy `_example.yaml`); the files are the list of workspaces CI deploys |
| `backend.hcl` | Where Terraform keeps state (written by `scripts/setup.py state`) |
| `setup.yaml` | The setup values (`docs/SETUP.md`, step 1) and the AI review's workspace and model; not read by Terraform |
