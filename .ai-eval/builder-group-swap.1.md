**Risk:** 🔴 **High**: builder access moves to a new group; anyone only in the old group loses workspace access.

> [!WARNING]
> Members of `ss1-cd-builders` who are not in `ss1-data-builders` lose workspace access, the SS1 Default Warehouse, the builder cluster policy and the catalog when this merges.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ♻️ | Builder workspace access and entitlements | `ss1-cd-builders` → `ss1-data-builders`; Workspace and SQL access | builders |
| ✏️ | SS1 Default Warehouse permissions | builder Can use: `ss1-cd-builders` → `ss1-data-builders`; explorers unchanged | builders |
| ✏️ | SS1 BUILDER Compute policy permissions | Can use: `ss1-cd-builders` → `ss1-data-builders` | builders |
| ✏️ | `ss1_citizen_dev` catalog grants | USE CATALOG, USE SCHEMA: `ss1-cd-builders` → `ss1-data-builders` | builders |

#### Check before merging
- In Entra ID, confirm that `ss1-data-builders` holds every current `ss1-cd-builders` member who should stay a builder. Anyone missing loses builder access on merge.
- The plan guard flags deletion of the old group's workspace assignment and entitlements. Approve with the label only once the membership check above is done.
- Schema-level data grants to `ss1-cd-builders` are not managed here. The inputs don't show them. Check whether they must be granted again to `ss1-data-builders`.
