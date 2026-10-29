**Risk:** 🔴 **High**: one-way disabling of legacy access, while preflight finds Hive schemas and DBFS mounts still in use.

> [!WARNING]
> Hive schemas finance_raw, hr_staging and sales and DBFS mounts /mnt/landing and /mnt/archive stop working, permanently after 30 days.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ➕ | Personas | Users consumer-only; explorers SQL; builders workspace and SQL; no publishers | ss1-cd-users, ss1-cd-explorers, ss1-cd-builders |
| ➕ | Catalog ss1_citizen_dev | Workspace-only; personas get USE CATALOG, USE SCHEMA | explorers, builders |
| ➕ | SS1 Default Warehouse | Serverless X-Small, 1–2 clusters, 5 min auto-stop | explorers, builders |
| ➕ | Usage policy SS1-0-SELF-SERVICE | Chargeback tags, APP_ID NONE | explorers, builders |
| ➕ | Classic cluster policies (Interactive, Jobs, Pipelines) | LTS only, max 4 workers, one cluster per person | users granted by the app |
| ➕ | Legacy access, DBFS root and mounts off; user isolation on | Hive and mounts blocked; permanent after 30 days | all users |
| ➕ | Workspace settings | Tokens admins-only, 90 days; Git allowlist; downloads allowed | all users |
| ➕ | Genie Code instructions and skill | Defaults plus build-tagged-assets skill | all users |

#### Check before merging
- Decide: migrate finance_raw, hr_staging, sales, /mnt/landing and /mnt/archive first, or set the three legacy settings to `null` in this file.
- The Git allowlist is still the placeholder `https://github.com/<org>/`, so Git folders cannot reach your real repositories until the baseline is fixed.
- Deviation: warehouse size Small → X-Small. The diff gives no reason. This means less capacity per cluster.
