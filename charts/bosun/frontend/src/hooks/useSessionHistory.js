import { useState, useEffect, useCallback } from "react";

// ── Session history hook ──────────────────────────────────────────────────
export function useSessionHistory() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/sessions?limit=50");
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch (e) {
      console.warn("Failed to load sessions:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load on mount
  useEffect(() => { refresh(); }, [refresh]);

  return { sessions, loading, refresh };
}
