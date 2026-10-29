**Risk:** 🟢 **Low**: Capacity increase on one warehouse; nothing removed, and another pull request can undo it.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | SQL warehouse "SS1 Default Warehouse" | Size: X-Small → Small | explorers (ss1-cd-explorers), builders (ss1-cd-builders) |

#### Check before merging
- `sql_warehouse.size: Small` now matches the baseline. Decide whether to delete these two lines so this workspace follows future baseline size changes.
