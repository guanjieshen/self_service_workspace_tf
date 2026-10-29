**Risk:** 🟢 **Low**: Default warehouse grows to the baseline size, updated in place; can be reverted by another pull request.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | SS1 Default Warehouse size | X-Small → Small; same warehouse, so dashboards, alerts and jobs keep working | explorers (ss1-cd-explorers), builders (ss1-cd-builders) |

#### Check before merging
- Decide whether to delete the `sql_warehouse: size` lines instead. Small now equals the baseline, but this override keeps the size at Small even if the baseline size changes.
