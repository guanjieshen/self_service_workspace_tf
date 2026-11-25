// The one way the page calls the server: JSON in and out, errors as messages people can read.
import { useCallback, useEffect, useState } from "react";

/** call("/api/x", { method: "POST", body: {...} }): the server's JSON, or an Error with its message. */
export async function call(path, { method = "GET", body } = {}) {
  const r = await fetch(path, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Something went wrong (${r.status}).`);
  return data;
}

/** useApi("/api/x"): { data, error, loading, reload }. A newer request wins over an older, slower one. */
export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let current = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    call(path).then((data) => current && setState({ data, error: null, loading: false }))
              .catch((e) => current && setState({ data: null, error: e.message, loading: false }));
    return () => { current = false; };
  }, [path, version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { ...state, reload };
}
