**Risk:** 🟡 **Medium**: baseline change tightens the token lifetime limit in every workspace; existing tokens are unaffected and it is reversible.

#### What changes

| | Change | Details | Affects |
|---|---|---|---|
| ✏️ | Maximum personal access token lifetime | 90 days → 30 days, new tokens only | Platform admins (only token creators) |

#### Check before merging

- New tokens will expire within 30 days. Confirm that any integration using platform admin tokens can be rotated that often. Existing tokens keep their current expiry.
- This baseline change applies to every workspace. Review each workspace's plan, not just self_service_1.
