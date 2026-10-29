**Risk:** 🔴 **High**: the plan deletes the "SS1 Classic Jobs" cluster policy instead of leaving it alone; this can't be cleanly undone.

> [!WARNING]
> Jobs clusters using "SS1 Classic Jobs" lose their policy; recreating it later gives it a new ID.

#### What changes

| | Change | Details | Affects |
|---|---|---|---|
| ➖ | Cluster policy "SS1 Classic Jobs" | Deleted; it had one cluster per person | Users granted classic jobs compute by the self-service app |

#### Check before merging

- `jobs: null` normally means "stop managing, keep as is", but the plan deletes the policy. Decide whether removing classic jobs compute here is intended. If not, don't merge.
- The inputs don't show which jobs or clusters use this policy or who was granted it. Check in the workspace before deleting.
- Deviation: the baseline gives every workspace a classic jobs policy; here it is turned off. The diff gives no reason.
