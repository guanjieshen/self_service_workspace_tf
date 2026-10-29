**Risk:** 🟢 **Low**: warehouse capacity increase back to the baseline size; nothing removed, and another pull request can undo it.

#### What changes

| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | SS1 Default Warehouse size | X-Small → Small (more capacity) | explorers (ss1-cd-explorers), builders (ss1-cd-builders) |

#### Check before merging

- `sql_warehouse.size: Small` now matches the baseline. Decide whether to delete this line so the workspace follows future baseline changes to warehouse size.
