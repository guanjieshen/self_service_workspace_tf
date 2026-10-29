**Risk:** 🟡 **Medium**: first apply with one-way legacy access disable; preflight finds nothing still using it.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ➕ | Personas | Consumer only; explorers SQL; builders workspace and SQL; no publishers | ss1-cd-users, ss1-cd-explorers, ss1-cd-builders |
| ➕ | Catalog `ss1_citizen_dev` | This workspace only; USE CATALOG, USE SCHEMA; platform admins own it | explorers, builders |
| ➕ | SS1 Default Warehouse | Serverless X-Small (baseline Small), 1–2 clusters, 5-minute auto-stop | explorers, builders |
| ➕ | Usage and cluster policies | `SS1-0-SELF-SERVICE`, three classic policies, chargeback tags, `APP_ID` NONE | explorers, builders |
| ➕ | Legacy access, DBFS root and mounts | Disabled; legacy access becomes permanent after 30 days | all users |
| ➕ | Admin settings | User isolation, 90-day tokens (admins only), Git allowlist, Unity Gateway | all users |
| ➕ | Genie Code | Default instructions and the build-tagged-assets skill | all users |

#### Check before merging
- Git allowlist still holds the placeholder `https://github.com/<org>/` (preflight). Replace it in the baseline first, or Git folders cannot reach your repositories.
- Plan guard: approve disabling legacy access with the label. Preflight found no Hive, DBFS mount or legacy cluster use. It becomes permanent after 30 days.
- Deviation: warehouse size Small → X-Small, no reason given. Decide whether explorers and builders can work with less capacity.
