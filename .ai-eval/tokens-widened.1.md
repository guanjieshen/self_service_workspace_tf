**Risk:** 🔴 **High**: lets builders create personal access tokens, a security-relevant deviation with no reason given; plan guard flagged it.

> [!WARNING]
> Builders gain personal access tokens for API access outside the workspace UI, loosening a baseline control without a stated reason.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | Personal access token permissions | Can use: platform admins → platform admins, builders | builders (`ss1-cd-builders`) |

#### Check before merging
- Deviation: builder can create tokens `false` → `true`. The diff gives no reason; get one from the requester before applying the plan-guard approval label.
- Decide whether the baseline's 90-day maximum token lifetime is acceptable for builder tokens, and who will watch builder token use.
