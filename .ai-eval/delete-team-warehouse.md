**Risk:** 🔴 **High**: deletes SS1 Data Eng Warehouse, which ss1-data-eng uses; re-adding it creates a new ID.

> [!WARNING]
> Dashboards, alerts, queries and jobs that run on SS1 Data Eng Warehouse will break. The data-eng team loses that warehouse.

#### What changes
| | Change | Details | Affects |
|---|---|---|---|
| ➖ | SQL warehouse SS1 Data Eng Warehouse | Serverless, X-Small, 1 cluster, 5-minute auto-stop; deleted | data-eng team (ss1-data-eng) |
| ➖ | Warehouse permissions | ss1-data-eng loses Can use | data-eng team (ss1-data-eng) |

#### Check before merging
- Find the dashboards, alerts, queries and jobs that use SS1 Data Eng Warehouse. Move them to SS1 Default Warehouse first, or they break.
- Check whether ss1-data-eng members are also in a persona group. Otherwise they lose all SQL warehouse access; the inputs don't show this.
- Approve the plan guard's warehouse-delete warning with the label only after the data-eng team confirms they no longer need it.
