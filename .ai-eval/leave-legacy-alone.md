**Risk:** 🟡 **Medium**: Legacy access is no longer enforced by the baseline, with a reason given. Nothing changes in the workspace now.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | Disable legacy access setting | Managed (disabled) → left unmanaged; workspace keeps current value (disabled) | Nobody now; future enforcement for all users |

#### Check before merging
- Deviation: disable legacy access `true` → `null` (unmanaged). A reason is given: the workspace is "still on Hive until the Q3 migration".
- Preflight says legacy access is **already disabled**, so Hive tables stay blocked after merging, because `null` doesn't re-enable access. If the team needs Hive, an admin must re-enable it by hand. That's only possible within 30 days of disabling, and the inputs don't show that date.
- Decide whether to merge at all. If Hive isn't actually needed, close this pull request and keep the baseline enforced. Otherwise, remove the line after the Q3 migration to restore enforcement.
