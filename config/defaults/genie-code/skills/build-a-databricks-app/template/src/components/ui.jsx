// The shared building blocks: build every screen from these. A new one goes here, styled in
// styles.css with the design tokens; never inline styles or another UI library.
import { useEffect, useId } from "react";

/** The page frame: the app's name (also the browser tab's title) and who is signed in. */
export function Shell({ title, user, children }) {
  useEffect(() => { document.title = title; }, [title]);
  return (
    <>
      <header className="shell-top"><div className="shell-top-inner">
        <span className="brand">{title}</span>{user && <span className="who">{user}</span>}
      </div></header>
      <main className="shell-main">{children}</main>
    </>
  );
}

/** A screen's title, and one line on what it is for. */
export function PageHead({ title, children }) {
  return <div className="page-head"><h1>{title}</h1>{children && <p>{children}</p>}</div>;
}

/** The app's screens as tabs. tabs: [{ key, label }]; the parent keeps which one is open. */
export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} type="button" role="tab" className="tab" aria-selected={t.key === active} onClick={() => onChange(t.key)}>{t.label}</button>
      ))}
    </div>
  );
}

/** A panel: a title, one action (a Button), then its content (flush: no padding, for tables and lists). */
export function Card({ title, action, children, flush }) {
  return (
    <section className="card">
      {title && <div className="card-head"><h2>{title}</h2>{action}</div>}
      <div className={flush ? "" : "card-body"}>{children}</div>
    </section>
  );
}

/** One number with its label (put several in a <div className="grid">). */
export function Stat({ label, value, hint }) {
  return <div className="card stat"><div className="stat-label">{label}</div><div className="stat-value">{value}</div>{hint && <div className="stat-hint">{hint}</div>}</div>;
}

/** A table. columns: [{ key, label, num }] (num: right-aligned); rows: objects with those keys. */
export function DataTable({ columns, rows }) {
  return (
    <table className="table">
      <thead><tr>{columns.map((c) => <th key={c.key} className={c.num ? "num" : ""}>{c.label}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={r.id ?? i}>{columns.map((c) => <td key={c.key} className={c.num ? "num" : ""}>{r[c.key]}</td>)}</tr>)}</tbody>
    </table>
  );
}

/** A button: type="submit" to send its form (a plain button otherwise); primary for the one main action. */
export function Button({ primary, type = "button", ...props }) {
  return <button type={type} className={primary ? "btn primary" : "btn"} {...props} />;
}

/** A labelled form control. children: a function given the control's id, so the label points at it. */
export function Field({ label, hint, children }) {
  const id = useId();
  return <div className="field"><label htmlFor={id}>{label}</label>{children(id)}{hint && <span className="hint">{hint}</span>}</div>;
}

/** A short status label. tone: "ok", "warn", "bad" or "neutral". */
export function Badge({ tone = "neutral", children }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

/** What a card shows when there is nothing yet. */
export function Empty({ title, children }) {
  return <div className="empty"><strong>{title}</strong>{children}</div>;
}

/** Placeholder lines while data loads. */
export function Loading({ rows = 4 }) {
  return <div className="card-body stack">{Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" />)}</div>;
}

/** An error message people can act on (nothing when there is none). */
export function ErrorNote({ children }) {
  return children ? <div className="notice error" role="alert">{children}</div> : null;
}

/** A card's content in its three states: loading, failed, or the data (children(data)). */
export function Async({ state, empty, children }) {
  if (state.loading && !state.data) return <Loading />;
  if (state.error) return <div className="card-body"><ErrorNote>{state.error}</ErrorNote></div>;
  if (empty && (!state.data || state.data.length === 0)) return <Empty title={empty} />;
  return children(state.data);
}

/** A value for a Stat from a useApi state: "…" while loading, "–" if it failed. */
export function statValue(state, pick) {
  return state.error ? "–" : state.data ? pick(state.data) : "…";
}
