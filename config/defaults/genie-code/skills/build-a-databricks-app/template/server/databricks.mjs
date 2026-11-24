// Databricks from the app's server: the SQL warehouse (Statement Execution API) and Lakebase
// (Postgres). Plain HTTPS and the pg driver: nothing else to install.
import pg from "pg";

const HOST = (process.env.DATABRICKS_HOST || "").replace(/^(?!https?:\/\/)/, "https://");

// ---- The app's own identity (its service principal): OAuth machine-to-machine ----
let cached = null;
export async function appToken() {
  if (cached && cached.expires > Date.now() + 60_000) return cached.token;
  const id = process.env.DATABRICKS_CLIENT_ID, secret = process.env.DATABRICKS_CLIENT_SECRET;
  if (!id || !secret) throw new Error("No app credentials: run this inside Databricks Apps.");
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

// ---- SQL warehouse ----
// userToken: the signed-in person's (req.headers["x-forwarded-access-token"], with the app's
// "sql" user scope): the query runs as them, so Unity Catalog decides what they see. Without it,
// it runs as the app, which then needs SELECT on the tables.
export async function sql(statement, params = {}, userToken = null) {
  const token = userToken || (await appToken());
  // Parameters are strings unless typed: a number in LIMIT (which takes INT, not BIGINT) or a comparison needs its type.
  const type = (v) => (typeof v === "number" ? (Number.isInteger(v) ? (Math.abs(v) < 2 ** 31 ? "INT" : "BIGINT") : "DOUBLE") : typeof v === "boolean" ? "BOOLEAN" : "STRING");
  const parameters = Object.entries(params).map(([name, value]) => (
    value === null ? { name, value: null, type: "STRING" } : { name, value: String(value), type: type(value) }));
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
  // Every value arrives as a string: numbers and booleans are turned back into them, by column type.
  const cols = res.manifest?.schema?.columns || [];
  const cast = (t, v) => (v === null ? null : /^(TINYINT|SHORT|SMALLINT|INT|LONG|BIGINT|FLOAT|DOUBLE|DECIMAL)/.test(t) ? Number(v) : t === "BOOLEAN" ? v === "true" : v);
  return (res.result?.data_array || []).map((row) => Object.fromEntries(cols.map((c, i) => [c.name, cast(c.type_name, row[i])])));
}

// ---- Lakebase (Postgres): the app's own data ----
// bigint and numeric columns arrive as strings: numbers here (safe for IDs and amounts in this range).
pg.types.setTypeParser(20, (v) => Number(v));
pg.types.setTypeParser(1700, (v) => Number(v));
// The database resource gives PGHOST, PGUSER, PGDATABASE, PGPORT; the password is a short-lived
// OAuth credential for LAKEBASE_ENDPOINT, asked for whenever the pool opens a connection.
export const db = new pg.Pool({
  host: process.env.PGHOST, port: Number(process.env.PGPORT || 5432),
  user: process.env.PGUSER, database: process.env.PGDATABASE,
  ssl: { rejectUnauthorized: false },
  password: async () => (await api("POST", "/api/2.0/postgres/credentials", { endpoint: process.env.LAKEBASE_ENDPOINT }, await appToken())).token,
  max: 5, idleTimeoutMillis: 30_000, maxLifetimeSeconds: 2700,   // well inside the credential's hour
});
