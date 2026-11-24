// The shared building blocks. Build pages from these; add a new one here, not inline styles.
export function Shell({ title, user, children }) {
  return (
    <>
      <header className="shell-top"><div className="shell-top-inner">
        <span className="brand">{title}</span>{user && <span className="who">{user}</span>}
      </div></header>
      <main className="shell-main">{children}</main>
    </>
  );
}
export function PageHead({ title, children }) {
  return <div className="page-head"><h1>{title}</h1>{children && <p>{children}</p>}</div>;
}
export function Card({ title, action, children, flush }) {
  return (
    <section className="card">
      {title && <div className="card-head"><h2>{title}</h2>{action}</div>}
      <div className={flush ? "" : "card-body"}>{children}</div>
    </section>
  );
}
export function Stat({ label, value, hint }) {
  return <div className="card stat"><div className="stat-label">{label}</div><div className="stat-value">{value}</div>{hint && <div className="stat-hint">{hint}</div>}</div>;
}
// columns: [{ key, label, num }]
export function DataTable({ columns, rows }) {
  return (
    <table className="table">
      <thead><tr>{columns.map((c) => <th key={c.key} className={c.num ? "num" : ""}>{c.label}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={r.id ?? i}>{columns.map((c) => <td key={c.key} className={c.num ? "num" : ""}>{r[c.key]}</td>)}</tr>)}</tbody>
    </table>
  );
}
export function Button({ primary, ...props }) {
  return <button className={primary ? "btn primary" : "btn"} {...props} />;
}
export function Field({ label, hint, children }) {
  return <div className="field"><label>{label}</label>{children}{hint && <span className="hint">{hint}</span>}</div>;
}
export function Empty({ title, children }) {
  return <div className="empty"><strong>{title}</strong>{children}</div>;
}
export function Loading({ rows = 4 }) {
  return <div className="card-body" style={{ display: "grid", gap: 12 }}>{Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" />)}</div>;
}
export function ErrorNote({ children }) {
  return children ? <div className="notice error" role="alert">{children}</div> : null;
}
// A card's content in its three states: loading, failed, or the data.
export function Async({ state, empty, children }) {
  if (state.loading && !state.data) return <Loading />;
  if (state.error) return <div className="card-body"><ErrorNote>{state.error}</ErrorNote></div>;
  if (empty && (!state.data || state.data.length === 0)) return <Empty title={empty} />;
  return children(state.data);
}
// A short status label: tone "ok", "warn" or "neutral".
export function Badge({ tone = "neutral", children }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
