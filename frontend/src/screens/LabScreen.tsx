import { useEffect, useState, useCallback, useRef } from "react";
import { api, timeOf, type QueueItem } from "../api";
import { Board, todayLong, ticketNo } from "../Board";
import { IconCheck } from "../icons";

const LAB_PROVIDER = "prov_lab";
const REFRESH_MS = 5000;

/** Tomorrow as yyyy-mm-dd — the default collection date offered to staff. */
function tomorrow(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const prettyDate = (ymd: string) =>
  new Date(`${ymd}T12:00:00`).toLocaleDateString("en-NG", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

export function LabScreen() {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  // The row whose collection date is being set, and the chosen date.
  const [confirming, setConfirming] = useState<{ id: string; date: string } | null>(null);
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

  // Results ready = close the visit with the collection date the patient
  // sees; Adam's notification leg texts them exactly when to come collect.
  const resultsReady = async (id: string, collectionDate: string) => {
    setBusy(id);
    busyRef.current = id;
    try {
      await api.closeVisit(id, "done", collectionDate);
      busyRef.current = null;
      setConfirming(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to mark results ready");
    } finally {
      busyRef.current = null;
      setBusy(null);
    }
  };

  return (
    <Board role="lab" title="Laboratory" count={queue.length} countLabel="waiting">
      <p className="context-line">
        <span className="context-date">{todayLong()}</span> — today's paid tests, in arrival
        order, details attached before the patient walks in.
      </p>

      {error && (
        <div className="banner-error" role="alert">
          Backend not reachable — {error}. Is the stub running on :3002?
        </div>
      )}

      {loading && (
        <div className="skeleton-list" aria-hidden="true">
          <i /><i /><i />
        </div>
      )}

      {!loading && !error && queue.length === 0 && (
        <div className="empty">
          No tests waiting. Paid lab bookings from WhatsApp and USSD land here on their own.
        </div>
      )}

      {queue.length > 0 && (
        <section className="panel" aria-label="Sample queue">
          <div className="panel-head">Sample queue</div>
          {queue.map((q) => (
            <div className="lrow" key={q.id}>
              <div className="qrow">
                <span className="qrow-no">{ticketNo(q.position)}</span>
                <span className="qrow-name">{q.patient_name}</span>
                <span className="qrow-service">{q.service_name}</span>
                <span className="qrow-time">{timeOf(q.slot_time)}</span>
                <span className={`chip chip-${q.status}`}>{q.status.replace("_", " ")}</span>
                {confirming?.id !== q.id && (
                  <button
                    className="btn btn-row"
                    disabled={busy === q.id}
                    onClick={() => setConfirming({ id: q.id, date: tomorrow() })}
                  >
                    <IconCheck size={16} /> Results ready
                  </button>
                )}
              </div>
              {q.test_details && <p className="lrow-details">{q.test_details}</p>}
              {confirming?.id === q.id && (
                <div className="collect">
                  <label className="collect-field">
                    <span className="collect-label">Collection date the patient sees</span>
                    <input
                      type="date"
                      className="collect-date"
                      value={confirming.date}
                      min={tomorrow()}
                      onChange={(e) => setConfirming({ id: q.id, date: e.target.value })}
                    />
                  </label>
                  <button
                    className="btn btn-accent"
                    disabled={busy === q.id || !confirming.date}
                    onClick={() => resultsReady(q.id, confirming.date)}
                  >
                    <IconCheck /> Ready — notify patient
                  </button>
                  <button className="btn" disabled={busy === q.id} onClick={() => setConfirming(null)}>
                    Back
                  </button>
                  {confirming.date && (
                    <span className="collect-hint">
                      Patient will be told to collect on {prettyDate(confirming.date)}.
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}
        </section>
      )}
    </Board>
  );
}
