# Working on config/

Read the repository's [AGENTS.md](../AGENTS.md) first. This folder is the organization's
configuration: in an installed instance it is the only place people (and agents helping
them) change. The full guide is [config/README.md](../config/README.md); this is the short version.

## The rule

A workspace changes a default by setting **the same key in its file of the same name**:
`config/workspaces/<name>/settings.yaml` over `config/defaults/settings.yaml`, and so on for
`access`, `compute`, `cost` and `catalog`.

- Maps merge key by key; a list or a value replaces the default.
- `null` means "Terraform leaves this alone". On a workspace that was already applied,
  the setting is released (it keeps its current value), never reset.
- A key the baseline does not have fails the plan with its name, so a typo cannot
  silently do nothing.
- Keys only a workspace has: `workspace.yaml` (identity: `bu`, `lob`, `host`,
  `account_id`, ...), `teams` (access.yaml), `team_warehouses` (compute.yaml).

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
| `defaults/access.yaml` | Personas, their groups and rights, folders, who may run the self-service jobs (`jobs.runners`) |
| `defaults/compute.yaml` | SQL warehouse, shared cluster, cluster policies |
| `defaults/cost.yaml` | Usage (budget) policies and tags |
| `defaults/catalog.yaml` | The workspace catalog, personal schemas |
| `defaults/settings.yaml` | Workspace admin and security settings |
| `defaults/genie-code/` | Genie Code instructions and skills for every workspace |
| `workspaces/<name>/` | One folder per workspace (`_example/` is the template; create one with `scripts/workspaces.py new`) |
| `ai-review.yaml` | The model the AI plan review uses |
| `backend.hcl` | Where Terraform keeps state (copy `backend.hcl.example`) |
