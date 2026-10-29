**Risk:** 🟡 **Medium**: baseline change shortens token lifetime for every workspace; only new tokens affected, reversible by another pull request.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | Maximum personal access token lifetime | 90 → 30 days, new tokens only; existing tokens keep expiry | Platform admins (only token creators) |

#### Check before merging
- Confirm no platform admin integration or automation requests tokens longer than 30 days. After this change it gets shorter tokens or fails.
- Plan rotation for tokens about to be renewed. Every new token needs replacing every 30 days, in every workspace.
- This is a baseline change, so each workspace gets its own plan. Check that each one shows only this setting changing.
