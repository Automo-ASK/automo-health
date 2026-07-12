import { useEffect, useState, useCallback } from "react";
import { api, timeOf, type QueueItem } from "../api";

export function DoctorScreen() {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      setQueue(await api.queue("prov_ade"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const close = async (id: string, state: "done" | "follow_up" | "admitted") => {
    setBusy(id);
    try {
      await api.closeVisit(id, state);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to close visit");
    } finally {
      setBusy(null);
    }
  };

  const next = queue.find((q) => q.is_next);
  const rest = queue.filter((q) => !q.is_next);

  return (
    <div className="screen">
      <header className="screen-head">
        <div>
          <h1>Today&apos;s clinic</h1>
          <p className="muted">Dr. Adeyemi · General Practice</p>
        </div>
        <div className="count-pill">
          <span className="count-num">{queue.length}</span>
          <span className="count-label">in queue</span>
        </div>
      </header>

      {loading && <p className="muted">Loading queue…</p>}
      {error && <div className="banner error">Backend not reachable — {error}. Is the stub running on :3002?</div>}

      {!loading && !error && queue.length === 0 && (
        <div className="empty">No patients in the queue right now.</div>
      )}

      {next && (
        <section className="now-card">
          <div className="now-label">Now seeing</div>
          <div className="now-name">{next.patient_name}</div>
          <div className="now-meta">
            {next.service_name} · {timeOf(next.slot_time)} · <span className="tag">{next.type}</span>
          </div>
          <div className="now-actions">
            <button className="btn primary" disabled={busy === next.id} onClick={() => close(next.id, "done")}>
              ✓ Done
            </button>
            <button className="btn" disabled={busy === next.id} onClick={() => close(next.id, "follow_up")}>
              Follow-up booked
            </button>
            <button className="btn" disabled={busy === next.id} onClick={() => close(next.id, "admitted")}>
              Admitted / procedure
            </button>
          </div>
          <p className="hint">Done fires only after consult, meds, and the next appointment are settled.</p>
        </section>
      )}

      {rest.length > 0 && (
        <section className="list">
          <div className="list-head">Up next</div>
          {rest.map((q) => (
            <div className="row" key={q.id}>
              <span className="row-pos">{q.position}</span>
              <span className="row-name">{q.patient_name}</span>
              <span className="row-service muted">{q.service_name}</span>
              <span className="row-time">{timeOf(q.slot_time)}</span>
              <span className={"status status-" + q.status}>{q.status.replace("_", " ")}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
