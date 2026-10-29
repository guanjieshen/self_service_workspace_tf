**Risk:** 🟡 **Medium**: First apply disables legacy access (permanent after 30 days); preflight found nothing still using it.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ➕ | Persona entitlements | explorers SQL; builders workspace+SQL; users Databricks One only | ss1-cd-explorers, ss1-cd-builders, ss1-cd-users |
| ➕ | Catalog `ss1_citizen_dev` | Workspace-only; USE CATALOG, USE SCHEMA for personas | explorers, builders |
| ➕ | SS1 Default Warehouse | Serverless X-Small, 1–2 clusters, 5 min auto-stop | explorers, builders |
| ➕ | SS1 Builder Compute policy | Max 4 workers, 60 min, 1 cluster per user | builders |
| ➕ | Usage policies SS1-SHARED, SS1-PLATFORM | SHARED for personas, PLATFORM for admins | explorers, builders, platform admins |
| ➕ | Legacy access, DBFS root and mounts | Disabled; Hive and mounts blocked | all users |
| ➕ | Security settings | Tokens admins only, 90 days; user isolation; Git allowlist | all users |
| ➕ | Genie Code instructions and skill | Default instructions, build-tagged-assets skill | all users |

#### Check before merging
- The Git allowlist is set to the placeholder `https://github.com/<org>/`, which matches no real repository. Replace it in the baseline before merging, or Git folders won't work.
- Decide on disabling legacy access, which the guard flagged. It becomes permanent after 30 days. Preflight found no Hive, mount or legacy-cluster use.
- Deviations with no reason given: warehouse size Small → X-Small, and shared cluster on → off. Builders will have only their policy cluster.
