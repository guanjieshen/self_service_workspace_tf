**Risk:** 🔴 **High**: members of ss1-cd-builders lose builder access unless they are also in ss1-data-builders.

> [!WARNING]
> Anyone in ss1-cd-builders but not ss1-data-builders loses workspace, warehouse, serverless and catalog access on merge.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ♻️ | Builder group in workspace | ss1-cd-builders → ss1-data-builders; Workspace and SQL access | builders |
| ✏️ | SS1 Default Warehouse access | Can use: ss1-cd-builders → ss1-data-builders | builders |
| ✏️ | Serverless usage policy SS1-0-SELF-SERVICE | Users: ss1-cd-builders → ss1-data-builders | builders |
| ✏️ | Catalog ss1_citizen_dev grants | USE CATALOG, USE SCHEMA: ss1-cd-builders → ss1-data-builders | builders |

#### Check before merging
- Confirm in Entra ID that ss1-data-builders contains everyone who should stay a builder. Old-group members not in ss1-cd-users or ss1-cd-explorers lose the workspace entirely.
- Schema grants, classic cluster policy users and team usage policies come from the self-service app. If they name ss1-cd-builders, they won't move to the new group. The inputs can't show this.
- The plan guard flagged both deletes, so a person must approve with the label. Another pull request can restore the old group, but access is lost until then.
