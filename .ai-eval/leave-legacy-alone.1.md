**Risk:** 🟡 **Medium**: security-relevant deviation (legacy access left unmanaged) with a reason given; nothing in the workspace changes.

#### What changes

| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | Disable legacy access: Terraform stops managing it | Stays disabled (current value); no longer enforced by Terraform | all users |

#### Check before merging

- Deviation: disable legacy access `true` → `null` (unmanaged). The reason given is "still on Hive until the Q3 migration".
- This does not restore Hive access. Preflight shows legacy access is already disabled, and `null` leaves it that way. To use Hive, someone must re-enable legacy access by hand. If it was disabled more than 30 days ago, that is permanent and cannot be undone; the inputs don't show when it was disabled.
- Decide whether this deviation is still wanted. If Hive cannot or will not be re-enabled, the release only stops Terraform from protecting the setting.
