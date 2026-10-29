**Risk:** 🟡 **Medium**: First apply; legacy access shutdown is one-way, but preflight found nothing still using it.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ➕ | Personas | Consumer, SQL, workspace+SQL access; no publisher group | ss1-cd-users, ss1-cd-explorers, ss1-cd-builders |
| ➕ | Catalog `ss1_citizen_dev` | This workspace only; USE CATALOG, USE SCHEMA; admins own | explorers, builders |
| ➕ | SS1 Default Warehouse | Serverless X-Small, 1–2 clusters, 5-minute auto-stop | explorers, builders |
| ➕ | Usage policy SS1-0-SELF-SERVICE | Tags APP_ID NONE, BUSINESS_UNIT SS1 | explorers, builders |
| ➕ | Classic cluster policies (3) | Interactive, Jobs, Pipelines; one cluster each, ≤4 workers | users granted by the self-service app |
| ➕ | Security settings | Legacy access, DBFS root and mounts off; user isolation on | all users |
| ➕ | Tokens, data handling | Tokens: platform admins only, 90 days; downloads allowed | all users |
| ➕ | Git, embedding, Genie Code | Git allowlist placeholder; no embedding domains; default instructions | all users |

#### Check before merging
- Git allowlist is still `https://github.com/<org>/`. Replace it in the baseline first, or nobody can use Git folders with your repositories.
- Disabling legacy access becomes permanent after 30 days. Preflight found nothing still using Hive or DBFS mounts. Approve with the label.
- Deviation: SQL warehouse size Small → X-Small. This means less capacity for explorers and builders. The diff gives no reason; decide whether it is wanted.
