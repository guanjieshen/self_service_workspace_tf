**Risk:** 🔴 **High**: builders may now create personal access tokens, a security deviation with no reason given.

> [!WARNING]
> Every member of ss1-cd-builders can create personal access tokens for up to 90 days, which run with their access from outside the workspace.

#### What changes

| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | Personal access token permissions | Can use: platform admins → platform admins, builders | builders (ss1-cd-builders) |

#### Check before merging

- Deviation: builder `can_create_tokens` false → true. The diff gives no reason. Ask for one in the pull request before you approve the security label.
- Decide whether builders need tokens for a specific integration.
