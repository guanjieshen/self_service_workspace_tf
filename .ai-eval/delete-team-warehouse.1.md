**Risk:** 🔴 **High**: deletes the SS1 Data Eng Warehouse; the data-eng team loses it, and recreating it gives a new ID.

> [!WARNING]
> Dashboards, alerts, jobs and queries that use SS1 Data Eng Warehouse will break, and ss1-data-eng loses Can use on it.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ➖ | SQL warehouse SS1 Data Eng Warehouse | Serverless X-Small, 1 cluster, auto-stop 5 min; deleted | data-eng team |
| ➖ | Warehouse permissions | ss1-data-eng Can use removed | ss1-data-eng |

#### Check before merging
- Find any dashboards, alerts, jobs or saved queries that use SS1 Data Eng Warehouse and move them to SS1 Default Warehouse first. The inputs don't show what uses it.
- Check whether ss1-data-eng members are also in ss1-cd-explorers or ss1-cd-builders. If not, they will have no SQL warehouse access after the merge.
- The plan matches the diff. The guard flags this delete, so it needs label approval. Undoing it means a new pull request, and the recreated warehouse gets a new ID.
