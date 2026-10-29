**Risk:** 🔴 **High**: disables legacy access, permanent after 30 days, while preflight finds Hive schemas and DBFS mounts in use.

> [!WARNING]
> Hive schemas finance_raw, hr_staging and sales and DBFS mounts /mnt/landing and /mnt/archive stop working at apply; no data is deleted.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ➕ | Persona entitlements | Consumer for users; SQL for explorers; workspace and SQL for builders | users, explorers, builders |
| ➕ | Catalog ss1_citizen_dev | Workspace-only; USE CATALOG, USE SCHEMA; admins all privileges | explorers, builders |
| ➕ | SS1 Default Warehouse | Serverless X-Small (baseline Small), 1–2 clusters, 5-minute auto-stop | explorers, builders |
| ➕ | Serverless usage policy SS1-0-SELF-SERVICE | Tags APP_ID NONE, BUSINESS_UNIT SS1 | explorers, builders |
| ➕ | Classic cluster policies (3) | Interactive, Jobs, Pipelines; one cluster per person, 4 workers | users granted by the app |
| ➕ | Security settings | Legacy access and DBFS off; user isolation; tokens admins only, 90 days | all users |
| ➕ | Data and sharing settings | Downloads, exports on; DBFS browser off; Git allowlist; Teams only | all users |
| ➕ | Genie Code instructions and skill | Default instructions; build-tagged-assets skill | all users |

#### Check before merging
- Decide whether to migrate the Hive schemas and DBFS mounts first, or set the three legacy settings to `null` in this workspace's file.
- The Git allowlist still has the placeholder `https://github.com/<org>/`. Replace it in the baseline, or Git folders cannot use your repositories.
- Deviation: the default warehouse is X-Small (baseline Small). It has less capacity, and the diff gives no reason.
