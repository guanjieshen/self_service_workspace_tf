// The app's screens. EXAMPLE: a data screen (the SQL warehouse) and a notes screen (Lakebase), as
// tabs. Replace them with the app's own; keep the patterns (useApi, Async, the ui.jsx components).
import { useState } from "react";
import { call, useApi } from "./api.js";
import { Async, Button, Card, DataTable, ErrorNote, Field, PageHead, Shell, Stat, Tabs, statValue } from "./components/ui.jsx";

const APP_TITLE = "Starter app";   // the app's name as people see it (also the browser tab's title)
const TABS = [{ key: "data", label: "Trips" }, { key: "notes", label: "Notes" }];

export default function App() {
  const me = useApi("/api/me");
  const [tab, setTab] = useState(TABS[0].key);
  return (
    <Shell title={APP_TITLE} user={me.data?.email}>
      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      {tab === "data" ? <TripsScreen /> : <NotesScreen />}
    </Shell>
  );
}

/** EXAMPLE screen: rows from the SQL warehouse, read as the signed-in person. */
function TripsScreen() {
  const trips = useApi("/api/trips?limit=10");
  const total = (rows) => rows.reduce((n, r) => n + r.trips, 0).toLocaleString();
  return (
    <>
      <PageHead title="Busiest pickup zips">Taxi trips from the SQL warehouse, read with your own access.</PageHead>
      <div className="grid"><Stat label="Trips (top 10 zips)" value={statValue(trips, total)} hint="samples.nyctaxi.trips" /></div>
      <Card title="By pickup zip" action={<Button onClick={trips.reload}>Refresh</Button>} flush>
        <Async state={trips} empty="No trips">
          {(rows) => <DataTable rows={rows} columns={[{ key: "pickup_zip", label: "Pickup zip" },
            { key: "trips", label: "Trips", num: true }, { key: "avg_fare", label: "Average fare", num: true }]} />}
        </Async>
      </Card>
    </>
  );
}

/** EXAMPLE screen: the app's own data, kept in Lakebase: a form and a list. */
function NotesScreen() {
  const notes = useApi("/api/notes");
  const [draft, setDraft] = useState(""), [saving, setSaving] = useState(false), [error, setError] = useState(null);

  async function save(e) {
    e.preventDefault();
    setSaving(true); setError(null);
    try { await call("/api/notes", { method: "POST", body: { body: draft } }); setDraft(""); notes.reload(); }
    catch (err) { setError(err.message); }
    finally { setSaving(false); }
  }

  return (
    <>
      <PageHead title="Notes">Notes the app keeps in its own database.</PageHead>
      <Card title="Add a note">
        <form className="form" onSubmit={save}>
          <Field label="Note">{(id) => <textarea id={id} rows={3} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="What did you notice?" />}</Field>
          <ErrorNote>{error}</ErrorNote>
          <div className="row"><Button primary type="submit" disabled={saving || !draft.trim()}>{saving ? "Saving…" : "Save note"}</Button></div>
        </form>
      </Card>
      <Card title="Latest notes" flush>
        <Async state={notes} empty="No notes yet">
          {(rows) => <ul className="list">{rows.map((n) => <li key={n.id}>{n.body}<div className="meta">{n.author} · {new Date(n.created_at).toLocaleString()}</div></li>)}</ul>}
        </Async>
      </Card>
    </>
  );
}
