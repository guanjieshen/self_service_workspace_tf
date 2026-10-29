**Risk:** 🟢 **Low**: in-place warehouse size increase that brings the workspace back to the baseline; easily reverted.

#### What changes

| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | SS1 Default Warehouse size | X-Small → Small; same warehouse ID, so dashboards, alerts and jobs keep working | explorers (ss1-cd-explorers), builders (ss1-cd-builders) |

#### Check before merging

- Decide whether to delete `sql_warehouse: size: Small` from `self_service_1.yaml`. It now equals the baseline, but keeping it pins the size here if the baseline changes later.
