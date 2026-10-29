**Risk:** 🔴 **High**: First apply disables legacy access (permanent after 30 days) while preflight finds Hive schemas and DBFS mounts in use.

> [!WARNING]
> The Hive schemas finance_raw, hr_staging and sales, and the mounts /mnt/landing and /mnt/archive, stop working. After 30 days this cannot be undone.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ➕ | Personas | users: Databricks One; explorers: SQL; builders: workspace and SQL | ss1-cd-users, ss1-cd-explorers, ss1-cd-builders |
| ➕ | SS1 Default Warehouse | Serverless X-Small (baseline Small), 1–2 clusters, 5-min auto-stop | explorers, builders |
| ➕ | SS1 Builder Compute policy | Max 4 workers, 60 min, one cluster; no shared cluster | builders |
| ➕ | Catalog ss1_citizen_dev | Workspace-only; personas get USE CATALOG and USE SCHEMA | explorers, builders |
| ➕ | Serverless usage policies | SS1-SHARED for personas; SS1-PLATFORM for admins | explorers, builders |
| ➕ | Security settings | Legacy access and DBFS off; user isolation, Unity Gateway on | all users |
| ➕ | Tokens, Git, data handling | Tokens for admins only, 90 days; Git allowlist; downloads on | all users |
| ➕ | Genie Code | Default instructions and build-tagged-assets skill | all users |

#### Check before merging
- Migrate finance_raw, hr_staging, sales, /mnt/landing and /mnt/archive first. Otherwise add `disable_legacy_access: null` and `disable_dbfs_root_and_mounts: null` under `settings:`.
- The Git allowlist is still the placeholder `https://github.com/<org>/`. Users cannot use your real repositories until the baseline URL is fixed.
- Decide on two deviations, neither with a reason given: warehouse Small → X-Small (less capacity), and shared cluster on → off (builders get only their policy).
