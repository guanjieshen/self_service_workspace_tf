**Risk:** 🔴 **High**: plan deletes the SS1 Classic Jobs cluster policy instead of leaving it alone; undoing it creates a new ID.

> [!WARNING]
> Jobs and clusters that use SS1 Classic Jobs lose their policy, and job definitions that reference its ID break.

#### What changes

| | Change | Details | Affects |
|---|---|---|---|
| ➖ | Cluster policy SS1 Classic Jobs | Deleted; it allowed one cluster per user | Users granted the policy by the self-service app |

#### Check before merging

- `jobs: null` looks like a request to leave the policy alone, but the plan deletes it. Decide whether deleting it is intended; if not, don't merge.
- If deleting it is intended, find the jobs and clusters that use SS1 Classic Jobs and move them to another policy. The inputs don't show which ones use it.
- Deviation: the baseline jobs policy, SS1 Classic Jobs (one cluster per user), → no jobs policy in this workspace. The diff gives no reason.
