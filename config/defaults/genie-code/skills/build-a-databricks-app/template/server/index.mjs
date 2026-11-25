// The app's server: its API under /api, and the built page (dist/) for everything else.
//
// The app's own routes go in the "Routes" section; the EXAMPLE routes show the patterns and are
// replaced by them. See AGENTS.md for the rules.
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { db, HAS_DB, IN_APP, sql } from "./databricks.mjs";

const app = express();
app.use(express.json({ limit: "1mb" }));

// ---- Helpers every route uses ----

/** Who is using the app (Databricks Apps signs people in and says who). */
const who = (req) => req.headers["x-forwarded-email"] || (IN_APP ? "unknown" : "local@example.com");
/** The signed-in person's token, for sql(): their queries run as them. */
const userToken = (req) => req.headers["x-forwarded-access-token"] || null;
/** A whole number from the query string, kept between min and max (a LIMIT, a page size). */
const intParam = (value, fallback, min, max) => Math.min(Math.max(Number.parseInt(value, 10) || fallback, min), max);
/** Wrap a route: its result as JSON, an error as { error } with a message people can read. */
const handle = (fn) => async (req, res) => {
  try { res.json(await fn(req)); }
  catch (e) { console.error(`${req.method} ${req.path}:`, e); res.status(e.status || 500).json({ error: String(e.message || e) }); }
};
/** An error the user caused (a bad input): sent as 400 with its message. */
const bad = (message) => Object.assign(new Error(message), { status: 400 });

// ---- The database's tables: made at start, each change added below (never edited) ----

let dbState = HAS_DB ? "starting" : "none";

async function migrate() {
  await db.query("CREATE SCHEMA IF NOT EXISTS app");
  // EXAMPLE table (with the notes routes below): replace it with the app's own.
  await db.query(`CREATE TABLE IF NOT EXISTS app.notes (
    id serial PRIMARY KEY, author text NOT NULL, body text NOT NULL, created_at timestamptz NOT NULL DEFAULT now())`);
  // A new column later: ALTER TABLE app.<table> ADD COLUMN IF NOT EXISTS <column> <type>;
}

/** migrate(), tried again every 15 seconds while the database wakes up or is still being made. */
async function migrateWhenReady(tries = 20) {
  try { await migrate(); dbState = "ready"; console.log("Database ready"); }
  catch (e) {
    console.error(`Database not ready (${e.message}): trying again in 15 seconds`);
    if (tries > 1) setTimeout(() => migrateWhenReady(tries - 1), 15_000); else dbState = "failed";
  }
}

// ---- Routes ----

app.get("/api/health", handle(async () => ({ ok: true, database: dbState })));
app.get("/api/me", handle(async (req) => ({ email: who(req), queries_run_as: userToken(req) ? "you" : "the app" })));

// EXAMPLE: data from the SQL warehouse, as the signed-in person. Replace it with the app's own query.
app.get("/api/trips", handle(async (req) => sql(
  `SELECT pickup_zip, count(*) AS trips, round(avg(fare_amount), 2) AS avg_fare
   FROM samples.nyctaxi.trips GROUP BY pickup_zip ORDER BY trips DESC LIMIT :n`,
  { n: intParam(req.query.limit, 10, 1, 100) }, userToken(req))));

// EXAMPLE: the app's own data, in Lakebase. Replace it with the app's own.
app.get("/api/notes", handle(async () => (await db.query(
  "SELECT id, author, body, created_at FROM app.notes ORDER BY id DESC LIMIT 50")).rows));
app.post("/api/notes", handle(async (req) => {
  const body = String(req.body?.body || "").trim().slice(0, 2000);
  if (!body) throw bad("Write something first.");
  return (await db.query("INSERT INTO app.notes (author, body) VALUES ($1, $2) RETURNING *", [who(req), body])).rows[0];
}));

// ---- The page ----

const dist = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "dist");
app.use(express.static(dist));
app.get(/^(?!\/api).*/, (_req, res) => res.sendFile(path.join(dist, "index.html")));

// What the app was given (names only, never values): the first line to read in its logs.
console.log("Settings:", ["DATABRICKS_HOST", "DATABRICKS_CLIENT_ID", "DATABRICKS_WAREHOUSE_ID", "PGHOST", "PGUSER", "PGDATABASE", "PGPORT", "LAKEBASE_ENDPOINT"]
  .map((k) => `${k}=${process.env[k] ? "set" : "missing"}`).join(" "));

// Listen first, so the app answers even while its database wakes up.
const port = Number(process.env.DATABRICKS_APP_PORT || 8000);
app.listen(port, () => console.log(`Listening on ${port}`));
if (HAS_DB) migrateWhenReady();
