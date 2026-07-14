import { useEffect, useState, useCallback, useRef } from "react";
import { api, timeOf, type QueueItem } from "../api";

const LAB_PROVIDER = "prov_lab";
const REFRESH_MS = 5000;

export function LabScreen() {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    if (busyRef.current) return;
    try {
      setError(null);
      setQueue(await api.queue(LAB_PROVIDER));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load lab queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  // "Results ready" closes the visit; Adam's notification leg texts the
  // patient that results are ready to collect.
  const resultsReady = async (id: string) => {
    setBusy(id);
    busyRef.current = id;
    try {
      await api.closeVisit(id, "done");
      busyRef.current = null;
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to mark results ready");
    } finally {
      busyRef.current = null;
      setBusy(null);
    }
  };

  return (
    <div className="screen">
      <header className="screen-head">
        <div>
          <h1>Lab</h1>
          <p className="muted">Today&apos;s paid tests, in arrival order</p>
        </div>
        <div className="count-pill">
          <span className="count-num">{queue.length}</span>
          <span className="count-label">waiting</span>
        </div>
      </header>

      {loading && <p className="muted">Loading lab queue…</p>}
      {error && <div className="banner error">Backend not reachable — {error}. Is the stub running on :3002?</div>}

      {!loading && !error && queue.length === 0 && (
        <div className="empty">No tests waiting. Paid lab bookings from WhatsApp and USSD land here on their own.</div>
      )}

      {queue.length > 0 && (
        <section className="list">
          <div className="list-head">Sample queue</div>
          {queue.map((q) => (
            <div className="row" key={q.id}>
              <span className="row-pos">{q.position}</span>
              <span className="row-name">{q.patient_name}</span>
              <span className="row-service muted">{q.service_name}</span>
              <span className="row-time">{timeOf(q.slot_time)}</span>
              <span className={"status status-" + q.status}>{q.status.replace("_", " ")}</span>
              <button className="btn small" disabled={busy === q.id} onClick={() => resultsReady(q.id)}>
                ✓ Results ready
              </button>
            </div>
          ))}
        </section>
      )}
      <p className="hint">Marking results ready closes the visit and queues the results-ready notification.</p>
    </div>
  );
}
