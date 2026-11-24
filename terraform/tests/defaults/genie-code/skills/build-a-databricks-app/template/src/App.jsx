// The example page: data from the SQL warehouse, and notes kept in Lakebase. Replace it with the app.
import { useState } from "react";
import { call, useApi } from "./api.js";
import { Async, Button, Card, DataTable, ErrorNote, Field, PageHead, Shell, Stat } from "./components/ui.jsx";

export default function App() {
  const me = useApi("/api/me");
  const trips = useApi("/api/trips?limit=10");
  const notes = useApi("/api/notes");
  const [draft, setDraft] = useState(""), [saving, setSaving] = useState(false), [error, setError] = useState(null);

  async function save(e) {
    e.preventDefault();
    setSaving(true); setError(null);
    try { await call("/api/notes", { method: "POST", body: { body: draft } }); setDraft(""); notes.reload(); }
    catch (err) { setError(err.message); }
    finally { setSaving(false); }
  }
  const total = (trips.data || []).reduce((n, r) => n + Number(r.trips), 0);

  return (
    <Shell title="Starter app" user={me.data?.email}>
      <PageHead title="Overview">Data from the SQL warehouse, and notes the app keeps in Lakebase.</PageHead>
      <div className="grid">
        <Stat label="Trips (top 10 zips)" value={trips.data ? total.toLocaleString() : "…"} hint="samples.nyctaxi.trips" />
        <Stat label="Notes" value={notes.data ? notes.data.length : "…"} hint="Lakebase: app.notes" />
      </div>
      <Card title="Busiest pickup zips" action={<Button onClick={trips.reload}>Refresh</Button>} flush>
        <Async state={trips} empty="No trips">
          {(rows) => <DataTable rows={rows} columns={[{ key: "pickup_zip", label: "Pickup zip" },
            { key: "trips", label: "Trips", num: true }, { key: "avg_fare", label: "Average fare", num: true }]} />}
        </Async>
      </Card>
      <Card title="Notes" flush>
        <form className="card-body form" onSubmit={save}>
          <Field label="Add a note"><textarea rows={3} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="What did you notice?" /></Field>
          <ErrorNote>{error}</ErrorNote>
          <div className="row"><Button primary disabled={saving || !draft.trim()}>{saving ? "Saving…" : "Save note"}</Button></div>
        </form>
        <Async state={notes} empty="No notes yet">
          {(rows) => <ul className="list">{rows.map((n) => <li key={n.id}>{n.body}<div className="meta">{n.author} · {new Date(n.created_at).toLocaleString()}</div></li>)}</ul>}
        </Async>
      </Card>
    </Shell>
  );
}
