#!/usr/bin/env python3
"""Try the database changes on a Lakebase dev branch before a pull request (never production).

  python3 tests/dev_branch.py --profile <cli profile> --project cd-self-service --branch dev

As yourself (signed in with the Databricks CLI; the credential is made here and never shown):

1. Fresh install: drops and recreates the self_service schema in the branch's empty default
   database (databricks_postgres), runs every migration, then again (nothing must run), and
   round-trips requests and settings through store.py.
2. Upgrade: runs the new migrations on the branch's copy of production's database
   (self_service), and checks no request was lost.

Your role on the branch needs DATABRICKS_SUPERUSER (Lakebase: the branch, Roles & Databases).
The grants are not tried here: that needs CREATEROLE, which the membership does not carry;
tests/test_db.py checks them on CI's Postgres. Not part of the test suite (not test_*.py).
"""
import argparse
import os
import pathlib
import sys
import uuid

APP = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(APP), str(APP / "db")]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--profile", required=True)
    p.add_argument("--project", default="cd-self-service")
    p.add_argument("--branch", default="dev")
    p.add_argument("--user", default=os.environ.get("PGUSER"), help="your email (default PGUSER)")
    a = p.parse_args(argv)
    if a.branch == "production":
        raise SystemExit("Not on production: use a dev branch.")
    import psycopg
    import migrate
    import settings
    import store
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient(profile=a.profile)
    endpoint = f"projects/{a.project}/branches/{a.branch}/endpoints/primary"
    host = w.postgres.get_endpoint(name=endpoint).status.hosts.host
    user = a.user or w.current_user.me().user_name
    token = lambda: w.postgres.generate_database_credential(endpoint=endpoint).token
    conn = lambda db, **kw: psycopg.connect(host=host, dbname=db, user=user, password=token(), sslmode="require", **kw)

    # 1. Fresh install, in the empty default database.
    with conn("databricks_postgres", autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS self_service CASCADE")
    with conn("databricks_postgres") as c:
        ran = migrate.run(c, {})
    with conn("databricks_postgres") as c:
        assert migrate.run(c, {}) == [], "a second run must change nothing"
    print("fresh install:", ", ".join(ran))
    db = store.Store({"host": host, "name": "databricks_postgres", "endpoint": endpoint}, credential=token,
                     connect=lambda token: psycopg.connect(host=host, dbname="databricks_postgres", user=user, password=token, sslmode="require"))
    rid = f"ss-{uuid.uuid4().hex[:8]}"
    db.record_request({"id": rid, "kind": "project_schema", "workspace": "dev", "bu": "DEV", "requested_by": user,
                       "name": "dev_check", "reason": "Trying the migrations on a dev branch."})
    assert db.decide(rid, "dana@contoso.com", "approved") and not db.decide(rid, "mo@contoso.com", "rejected")
    assert [r["state"] for r in db.requests_in(["DEV"]) if r["id"] == rid] == ["approved"]
    db.set_settings([("faq.data", "https://wiki.example.com/faq"), ("faq.data", None)], "dana@contoso.com")
    assert db.settings()["faq.data"]["value"] is None
    latest = db.setting_history(q="wiki.example", keys=["faq.data"])[0]
    assert (latest["value"], latest["previous"], latest["first"]) == (None, "https://wiki.example.com/faq", False)
    assert db.setting_history(keys=["banner.text"]) == []
    assert settings.apply({"faq": {"data": "https://yaml.example.com"}}, db.settings())["faq"]["data"] == "https://yaml.example.com"
    print("store round trip: ok")

    # 2. Upgrade, on the branch's copy of production.
    with conn("self_service") as c:
        before = c.execute("SELECT count(*) FROM self_service.requests").fetchone()[0]
        ran = migrate.run(c, {})
    with conn("self_service") as c:
        after = c.execute("SELECT count(*) FROM self_service.requests").fetchone()[0]
    assert after == before, f"requests before {before}, after {after}"
    print(f"upgrade: {', '.join(ran) or 'nothing new'}; {after} requests kept")


if __name__ == "__main__":
    main()
