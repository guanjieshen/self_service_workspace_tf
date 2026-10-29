**Risk:** 🔴 **High**: builders may now create personal access tokens, a loosened security control with no reason given.

> [!WARNING]
> Every member of ss1-cd-builders can create personal access tokens and reach the workspace through the API, outside the browser and its controls.

#### What changes

| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | Token permissions | Can use: platform admins → platform admins, builders | builders (ss1-cd-builders) |

#### Check before merging

- Deviation: builder token creation `false` → `true`. The diff gives no reason. Get the business justification and record it as a comment in the file before applying the approval label.
- Membership of ss1-cd-builders in Entra ID now decides who can hold tokens. Confirm that the group contains only the people who need API access.
- New tokens can last up to 90 days. If you later reverse this, the inputs do not show whether tokens already issued stay valid. Decide how you would revoke them.
