// Databricks, from the app's server: the SQL warehouse (the Statement Execution API) and the app's
// own Lakebase database (Postgres). Plain HTTPS and the pg driver: nothing else to install.
//
// You rarely change this file: the routes in index.mjs call sql() and db.query(). See AGENTS.md.
import pg from "pg";

const HOST = (process.env.DATABRICKS_HOST || "").replace(/^(?!https?:\/\/)/, "https://");
// Inside Databricks Apps (not on a laptop): the platform sets DATABRICKS_APP_NAME.
export const IN_APP = Boolean(process.env.DATABRICKS_APP_NAME);

// ---- The app's own identity (its service principal): OAuth machine-to-machine ----

let cached = null;

/** An access token for the app itself, kept until a minute before it expires. */
export async function appToken() {
  if (cached && cached.expires > Date.now() + 60_000) return cached.token;
  const id = process.env.DATABRICKS_CLIENT_ID, secret = process.env.DATABRICKS_CLIENT_SECRET;
  if (!id || !secret) throw new Error("No app credentials: this runs inside Databricks Apps.");
  const r = await fetch(`${HOST}/oidc/v1/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded",
               Authorization: "Basic " + Buffer.from(`${id}:${secret}`).toString("base64") },
    body: "grant_type=client_credentials&scope=all-apis",
  });
  if (!r.ok) throw new Error(`Signing in as the app failed: ${r.status} ${await r.text()}`);
  const j = await r.json();
  cached = { token: j.access_token, expires: Date.now() + j.expires_in * 1000 };
  return cached.token;
}

/** A Databricks REST call; errors carry Databricks' own message. */
async function api(method, path, body, token) {
  const r = await fetch(`${HOST}${path}`, {
    method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  const data = text ? JSON.parse(text) : {};
  if (!r.ok) throw new Error(data.message || `${method} ${path}: ${r.status}`);
  return data;
}

// ---- The SQL warehouse ----

// Parameters are text unless typed: a number in LIMIT (which takes INT, not BIGINT) or a comparison needs its type.
const typeOf = (v) => (typeof v === "number" ? (Number.isInteger(v) ? (Math.abs(v) < 2 ** 31 ? "INT" : "BIGINT") : "DOUBLE")
  : typeof v === "boolean" ? "BOOLEAN" : "STRING");
// Every value comes back as text: numbers and booleans are turned back into them, by column type.
const NUMERIC = new Set(["BYTE", "TINYINT", "SHORT", "SMALLINT", "INT", "INTEGER", "LONG", "BIGINT", "FLOAT", "DOUBLE", "DECIMAL"]);
const cast = (type, v) => (v === null ? null : NUMERIC.has(type) ? Number(v) : type === "BOOLEAN" ? v === "true" : v);

async function run(statement, params, token) {
  const parameters = Object.entries(params).map(([name, value]) => (
    value === null ? { name, value: null, type: "STRING" } : { name, value: String(value), type: typeOf(value) }));
  let res = await api("POST", "/api/2.0/sql/statements", {
    warehouse_id: process.env.DATABRICKS_WAREHOUSE_ID, statement, parameters,
    wait_timeout: "30s", on_wait_timeout: "CONTINUE", format: "JSON_ARRAY", disposition: "INLINE",
  }, token);
  // A stopped warehouse takes a minute to start: keep asking, up to two minutes.
  for (let i = 0; ["PENDING", "RUNNING"].includes(res.status?.state) && i < 120; i++) {
    await new Promise((ok) => setTimeout(ok, 1000));
    res = await api("GET", `/api/2.0/sql/statements/${res.statement_id}`, null, token);
  }
  if (res.status?.state !== "SUCCEEDED") throw new Error(res.status?.error?.message || `The query ${res.status?.state}`);
  const cols = res.manifest?.schema?.columns || [];
  return (res.result?.data_array || []).map((row) => Object.fromEntries(cols.map((c, i) => [c.name, cast(c.type_name, row[i])])));
}

/**
 * A query as the signed-in person: Unity Catalog decides what they may read. userToken is
 * req.headers["x-forwarded-access-token"] (the app's "sql" user scope). Rows as objects.
 * Use named parameters (:zip) in the statement, never values pasted into it.
 */
export async function sql(statement, params = {}, userToken = null) {
  if (!userToken && IN_APP) {
    throw new Error("This app can't read data for you yet: reload the page and allow it to use your data. "
      + "If that doesn't help, ask the app's owner to deploy it again.");
  }
  return run(statement, params, userToken || (await appToken()));
}

/** A query as the app itself, for data every user may see through the app. It needs SELECT on the tables. */
export async function sqlAsApp(statement, params = {}) {
  return run(statement, params, await appToken());
}

// ---- Lakebase (Postgres): the app's own data ----

// bigint and numeric columns arrive as strings: numbers here (safe for IDs and amounts in this range).
pg.types.setTypeParser(20, (v) => Number(v));
pg.types.setTypeParser(1700, (v) => Number(v));

// Deployed with a database (deploy(..., lakebase=True)): LAKEBASE_ENDPOINT is set, and the platform
// sets PGHOST, PGUSER, PGDATABASE and PGPORT. The password is a short-lived OAuth credential, asked
// for whenever the pool opens a connection.
export const HAS_DB = Boolean(process.env.LAKEBASE_ENDPOINT);

const pool = HAS_DB ? new pg.Pool({
  host: process.env.PGHOST, port: Number(process.env.PGPORT || 5432),
  user: process.env.PGUSER, database: process.env.PGDATABASE, ssl: true,
  password: async () => (await api("POST", "/api/2.0/postgres/credentials", { endpoint: process.env.LAKEBASE_ENDPOINT }, await appToken())).token,
  max: 5, idleTimeoutMillis: 30_000, connectionTimeoutMillis: 15_000,
  maxLifetimeSeconds: 2700,   // well inside the credential's hour
}) : null;
// A connection the database closed (it suspends after 5 idle minutes) must not crash the server.
pool?.on("error", (e) => console.error("Lakebase connection closed:", e.message));

/** The database: db.query(text, [values]) with $1 placeholders. */
export const db = {
  async query(text, values) {
    if (!pool) throw new Error("This app has no database: deploy it with lakebase=True to keep data.");
    return pool.query(text, values);
  },
};
