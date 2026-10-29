**Risk:** 🟡 **Medium**: baseline change tightens the token lifetime control in every workspace; only new tokens are affected.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | Maximum personal access token lifetime | 90 → 30 days, for new tokens only; existing tokens keep their expiry | Platform admins (ss1_platform_admins), the only token creators |

#### Check before merging
- Decide whether platform admins can rotate tokens every 30 days. Any integration they run on a token will need a new token sooner.
- This is a baseline change, so every workspace gets its own plan. Approve each plan, not only this one.
