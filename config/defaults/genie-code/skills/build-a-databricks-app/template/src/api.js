// One way to call the server: JSON in and out, errors as messages people can read.
import { useCallback, useEffect, useState } from "react";

export async function call(path, { method = "GET", body } = {}) {
  const r = await fetch(path, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Something went wrong (${r.status}).`);
  return data;
}

// useApi("/api/x"): { data, error, loading, reload }
export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const reload = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    call(path).then((data) => setState({ data, error: null, loading: false }))
              .catch((e) => setState({ data: null, error: e.message, loading: false }));
  }, [path]);
  useEffect(reload, [reload]);
  return { ...state, reload };
}
