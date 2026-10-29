**Risk:** 🟡 **Medium**: first apply; legacy access becomes permanently off after 30 days, but preflight found nothing using it.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ➕ | Personas | users Consumer; explorers SQL; builders Workspace and SQL; no publishers | ss1-cd-users, ss1-cd-explorers, ss1-cd-builders |
| ➕ | Catalog `ss1_citizen_dev` | Isolated to this workspace; USE CATALOG, USE SCHEMA | explorers, builders |
| ➕ | SS1 Default Warehouse | Serverless X-Small (baseline Small), 1–2 clusters, 5-min auto-stop | explorers, builders |
| ➕ | SS1 Builder Compute policy | Up to 4 workers, 60 min, one cluster per user | builders |
| ➕ | Usage policies SS1-SHARED, SS1-PLATFORM | SHARED / PLATFORM tags | personas / platform admins |
| ➕ | Security settings | Legacy access and DBFS off; user isolation; Unity Gateway enforced | all users |
| ➕ | Data and token settings | Downloads and exports on; tokens: platform admins only, 90 days | all users |
| ➕ | Genie Code | Default instructions and build-tagged-assets skill | all users |

#### Check before merging
- Git allowlist is still the placeholder `https://github.com/<org>/`. Merging restricts Git folders to it, blocking real repositories. Fix the baseline first.
- Legacy access off becomes permanent after 30 days. Preflight found no Hive or DBFS mount use. Confirm the team has no planned Hive use.
- No shared cluster (baseline: enabled), and no reason is given. Confirm builders need only their policy cluster.
