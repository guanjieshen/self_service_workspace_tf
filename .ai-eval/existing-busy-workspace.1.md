**Risk:** 🔴 **High**: first apply disables legacy access and DBFS mounts while preflight finds Hive schemas and mounts still in use.

> [!WARNING]
> Notebooks, queries and jobs that use Hive schemas `finance_raw`, `hr_staging`, `sales` or mounts `/mnt/landing`, `/mnt/archive` will stop working. After 30 days, legacy access cannot be turned back on.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ➕ | Personas | users Databricks One, explorers SQL, builders workspace; no publishers | ss1-cd-users, ss1-cd-explorers, ss1-cd-builders |
| ➕ | Catalog `ss1_citizen_dev` | This workspace only; personas get USE CATALOG, USE SCHEMA | explorers, builders |
| ➕ | SS1 Default Warehouse | Serverless, X-Small (baseline Small), workspace default | explorers, builders |
| ➕ | SS1 Builder Compute policy | No shared cluster (baseline has one) | builders |
| ➕ | Usage policies | SS1-SHARED, SS1-PLATFORM | all users |
| ➕ | Legacy access, DBFS root and mounts | Disabled; legacy access permanent after 30 days | all users |
| ➕ | Security settings | User isolation; tokens admins only, 90 days; Git allowlist | all users |
| ➕ | Genie Code | Default instructions and tagging skill | all users |

#### Check before merging
- Before merging, migrate the Hive schemas and mounts, or set `disable_legacy_access: null` and `disable_dbfs_root_and_mounts: null` under `settings:` in this workspace's file.
- The Git allowlist is still the placeholder `https://github.com/<org>/`. Git folders cannot reach your real repositories until it is replaced in the baseline.
- Confirm these choices: no publishers, and no shared cluster, so builders get only policy clusters.
