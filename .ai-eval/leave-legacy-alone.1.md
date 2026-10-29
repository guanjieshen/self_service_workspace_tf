**Risk:** 🟡 **Medium**: Security-relevant deviation (legacy access left unmanaged), reason given; nothing in the workspace changes.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | Disable legacy access | Managed (true) → left unmanaged; stays disabled | Nobody now; all users if changed by hand |

#### Check before merging
- Deviation: disable legacy access `true` → `null`. Reason given: "still on Hive until the Q3 migration."
- Preflight says legacy access is **already disabled**, so Hive is already blocked. This PR won't re-enable it; someone must do that by hand.
- Disabled legacy access becomes permanent after 30 days, and the inputs don't show when it was disabled. If Hive is needed, re-enable it by hand quickly.
