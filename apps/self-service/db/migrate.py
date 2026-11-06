#!/usr/bin/env python3
"""Bring the self-service database up to date: run each migration once, then the grants.

Run by scripts/app_deploy.py after the hub's bundle deploys, as the deploying identity, which owns the
database:

  migrate.py --host <endpoint host> --database self_service --user <owner> \\
             --endpoint projects/<p>/branches/production/endpoints/primary \\
             --grant self_service=<app role> [--grant approvals=<app role>]

It signs in with a short-lived Lakebase credential made for the endpoint (no password is
stored anywhere). For tests: --dsn postgresql://... instead of --host/--user/--endpoint.

migrations/NNN_name.sql run once each, in order, each in its own transaction, recorded in
self_service.schema_migrations. Never edit one that has run: add the next. grants.sql runs
every time, so a role that appears later (a new app) is granted on the next deploy.
"""
import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
MIGRATIONS = HERE / "migrations"
GRANTS = HERE / "grants.sql"
ROLES = ("self_service", "approvals", "readers")   # readers: several, comma-separated


def migrations():
    """The migration files, in order: 001_x.sql, 002_y.sql, ..."""
    files = sorted(MIGRATIONS.glob("*.sql"))
    for f in files:
        if not re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", f.name):
            raise SystemExit(f"{f.name}: migrations are named NNN_name.sql")
    numbers = [f.name[:3] for f in files]
    if len(set(numbers)) != len(numbers):
        raise SystemExit("two migrations share a number")
    return files


def grant_statements(roles):
    """grants.sql with the roles filled in; lines for a role that is not given are skipped, and
    a line for readers runs once per reader. Each statement is returned with its role names, to
    quote as identifiers when it runs."""
    out = []
    for line in GRANTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        wanted = re.findall(r"\{(\w+)\}", line)
        unknown = [w for w in wanted if w not in ROLES]
        if unknown:
            raise SystemExit(f"grants.sql: unknown role {unknown[0]}")
        if not all(roles.get(w) for w in wanted):
            continue
        if "readers" in wanted:
            for reader in [r for r in roles["readers"].split(",") if r]:
                out.append((line, {**{w: roles[w] for w in wanted if w != "readers"}, "readers": reader}))
        else:
            out.append((line, {w: roles[w] for w in wanted}))
    return out


def connect(args):
    import psycopg
    if args.dsn:
        return psycopg.connect(args.dsn, autocommit=False)
    from databricks.sdk import WorkspaceClient
    token = WorkspaceClient().postgres.generate_database_credential(endpoint=args.endpoint).token
    return psycopg.connect(host=args.host, dbname=args.database, user=args.user, password=token,
                           sslmode="require", autocommit=False)


def run(conn, roles):
    from psycopg import sql
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS self_service")
        cur.execute("CREATE TABLE IF NOT EXISTS self_service.schema_migrations "
                    "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        conn.commit()
        cur.execute("SELECT name FROM self_service.schema_migrations")
        done = {r[0] for r in cur.fetchall()}
    applied = []
    for f in migrations():
        if f.name in done:
            continue
        with conn.cursor() as cur:
            cur.execute(f.read_text())
            cur.execute("INSERT INTO self_service.schema_migrations (name) VALUES (%s)", (f.name,))
        conn.commit()
        applied.append(f.name)
    with conn.cursor() as cur:
        for statement, names in grant_statements(roles):
            # Role names are identifiers (quoted), never text pasted into SQL.
            cur.execute(sql.SQL(statement).format(**{k: sql.Identifier(v) for k, v in names.items()}))
    conn.commit()
    return applied


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dsn")
    p.add_argument("--host")
    p.add_argument("--database", default="self_service")
    p.add_argument("--user")
    p.add_argument("--endpoint")
    p.add_argument("--grant", action="append", default=[], metavar="ROLE=NAME")
    args = p.parse_args(argv)
    roles = dict(g.split("=", 1) for g in args.grant)
    unknown = set(roles) - set(ROLES)
    if unknown:
        p.error(f"unknown role {sorted(unknown)[0]} (known: {', '.join(ROLES)})")
    if not args.dsn and not (args.host and args.user and args.endpoint):
        p.error("give --dsn, or --host, --user and --endpoint")
    with connect(args) as conn:
        applied = run(conn, roles)
    print(f"migrations applied: {', '.join(applied) or 'none (up to date)'}; grants: {', '.join(sorted(r for r in roles if roles[r])) or 'none'}")


if __name__ == "__main__":
    sys.exit(main())
