**Risk:** 🔴 **High**: builders may now create personal access tokens, loosening a baseline security control with no reason given.

> [!WARNING]
> Every builder could create personal access tokens, valid up to 90 days, giving API access outside the browser session.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | Personal access token permissions | Can use: platform admins → platform admins + builders | builders (`ss1-cd-builders`) |

#### Check before merging
- Deviation: builder token creation `false` → `true`. The diff gives no reason. Decide whether builders need tokens, and record why in the workspace file.
- Membership of `ss1-cd-builders` in Entra ID now decides who can create tokens. Confirm that the group holds only people who should have API access.
- This needs a plan-guard approval label. Reverting the line later stops new tokens, but tokens already created stay valid until they expire.
