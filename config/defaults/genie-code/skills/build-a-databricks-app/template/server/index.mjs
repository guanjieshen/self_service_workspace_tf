// The app's server: the API under /api, the built page (dist/) for everything else.
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { db, sql } from "./databricks.mjs";

const app = express();
app.use(express.json());
const who = (req) => req.headers["x-forwarded-email"] || "local@example.com";
const userToken = (req) => req.headers["x-forwarded-access-token"] || null;
const handle = (fn) => async (req, res) => {
  try { res.json(await fn(req)); }
  catch (e) { console.error(e); res.status(500).json({ error: String(e.message || e) }); }
};

// The app's own tables, made once at start (the app owns its schema in Lakebase).
async function migrate() {
  await db.query("CREATE SCHEMA IF NOT EXISTS app");
  await db.query(`CREATE TABLE IF NOT EXISTS app.notes (
    id serial PRIMARY KEY, author text NOT NULL, body text NOT NULL, created_at timestamptz NOT NULL DEFAULT now())`);
}

app.get("/api/health", handle(async () => ({ ok: true, db: (await db.query("SELECT 1 AS ok")).rows[0].ok === 1 })));
app.get("/api/me", handle(async (req) => ({ email: who(req), queries_run_as: userToken(req) ? "you" : "the app" })));

// ---- Example: data from the SQL warehouse ----
app.get("/api/trips", handle(async (req) => sql(
  `SELECT pickup_zip, count(*) AS trips, round(avg(fare_amount), 2) AS avg_fare
   FROM samples.nyctaxi.trips GROUP BY pickup_zip ORDER BY trips DESC LIMIT :n`,
  { n: Math.min(Number(req.query.limit) || 10, 100) }, userToken(req))));

// ---- Example: the app's own data in Lakebase ----
app.get("/api/notes", handle(async () => (await db.query("SELECT id, author, body, created_at FROM app.notes ORDER BY id DESC LIMIT 50")).rows));
app.post("/api/notes", handle(async (req) => {
  const body = String(req.body?.body || "").trim().slice(0, 2000);
  if (!body) throw new Error("Write something first.");
  return (await db.query("INSERT INTO app.notes (author, body) VALUES ($1, $2) RETURNING *", [who(req), body])).rows[0];
}));

const dist = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "dist");
app.use(express.static(dist));
app.get(/^(?!\/api).*/, (_req, res) => res.sendFile(path.join(dist, "index.html")));

// What the app was given (names only, never values): the first thing to read in its logs.
console.log("Settings:", ["DATABRICKS_HOST", "DATABRICKS_CLIENT_ID", "DATABRICKS_WAREHOUSE_ID", "PGHOST", "PGUSER", "PGDATABASE", "PGPORT", "LAKEBASE_ENDPOINT"]
  .map((k) => `${k}=${process.env[k] ? "set" : "missing"}`).join(" "));
const port = Number(process.env.DATABRICKS_APP_PORT || 8000);
migrate().catch((e) => console.error("Lakebase is not ready:", e.message))
  .finally(() => app.listen(port, () => console.log(`Listening on ${port}`)));
