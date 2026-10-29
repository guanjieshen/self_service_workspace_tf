**Risk:** 🟡 **Medium**: Baseline change shortens new token lifetime in every workspace; reversible, existing tokens unaffected.

#### What changes

| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | Maximum personal access token lifetime | 90 → 30 days, new tokens only | Platform admins (ss1_platform_admins), the only token creators |

#### Check before merging

- Find integrations or scripts that use platform-admin personal access tokens. Tokens created after merge expire within 30 days, so they need rotating three times as often.
- This change applies to every workspace. Confirm each workspace's plan shows only this setting change.
