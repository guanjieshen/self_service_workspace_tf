**Risk:** 🔴 **High**: builders move to a new group; old group members not in it lose all workspace access.

> [!WARNING]
> Members of `ss1-cd-builders` who are not in `ss1-data-builders` lose workspace access, the warehouse, serverless compute and the catalog.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ♻️ | Builder workspace assignment and entitlements | `ss1-cd-builders` → `ss1-data-builders`; workspace and SQL access | builders |
| ✏️ | SS1 Default Warehouse permissions | Can use: `ss1-cd-builders` → `ss1-data-builders` | builders |
| ✏️ | SS1-0-SELF-SERVICE serverless usage policy users | `ss1-cd-builders` → `ss1-data-builders` | builders |
| ✏️ | `ss1_citizen_dev` catalog grants | USE CATALOG, USE SCHEMA: `ss1-cd-builders` → `ss1-data-builders` | builders |

#### Check before merging
- In Entra ID, confirm that everyone in `ss1-cd-builders` who should stay a builder is in `ss1-data-builders`. Anyone left out loses access as soon as this merges.
- Check whether the self-service app granted schemas, team policies or classic cluster policies to `ss1-cd-builders`. This change does not move those grants.
