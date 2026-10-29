**Risk:** 🟡 **Medium**: a security-relevant deviation (legacy access left unmanaged) with a reason; the workspace itself does not change.

#### What changes

| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | Disable legacy access: Terraform stops managing it | managed (disabled) → unmanaged; stays disabled, nothing changes in the workspace | all users |

#### Check before merging

- Deviation: disable legacy access `true` → `null` (unmanaged). The reason is given: Hive is still in use until the Q3 migration.
- This does not meet that intent. Preflight shows legacy access is already disabled, and `null` does not re-enable it. To keep Hive working, someone must re-enable it by hand.
- Disabling becomes permanent 30 days after it was set. The inputs do not show when that was, so check promptly if Hive is still needed.
