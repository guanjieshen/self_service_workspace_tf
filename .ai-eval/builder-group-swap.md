**Risk:** 🔴 **High**: builder access moves to a new group; members of ss1-cd-builders lose workspace access unless also in ss1-data-builders.

> [!WARNING]
> Anyone in ss1-cd-builders but not ss1-data-builders loses workspace access, the default warehouse, the builder compute policy and catalog access.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ♻️ | Builder group workspace assignment and entitlements | ss1-cd-builders → ss1-data-builders; workspace and SQL access | builders |
| ✏️ | SS1 Default Warehouse permissions | Can use: ss1-cd-builders → ss1-data-builders; explorers unchanged | builders |
| ✏️ | SS1 Builder Compute policy permissions | Can use: ss1-cd-builders → ss1-data-builders | builders |
| ✏️ | ss1_citizen_dev catalog grants | USE CATALOG, USE SCHEMA: ss1-cd-builders → ss1-data-builders | builders |

#### Check before merging
- Compare ss1-data-builders and ss1-cd-builders membership in Entra ID. Anyone missing from the new group loses builder access when this merges.
- The plan guard flags removing ss1-cd-builders' workspace access and entitlements. Approve it with the label only after the membership check. Another pull request can restore the old group.
- Decide whether any schema grants or object ownership that the self-service app gave to ss1-cd-builders must move to the new group. They don't appear in this plan.
