import { useEffect, useState, useCallback, useRef } from "react";
import { api, timeOf, type QueueItem, type Emergency } from "../api";
import { Board, todayLong, ticketNo } from "../Board";
import { IconCheck } from "../icons";

const DOCTORS = [
  { id: "prov_ade", name: "Dr. Adeyemi", specialty: "General Practice" },
  { id: "prov_ola", name: "Dr. Olamide", specialty: "General Practice" },
];

const REFRESH_MS = 5000;

const minutesAgo = (iso: string) => {
  const m = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60_000));
  return m === 0 ? "just now" : m === 1 ? "1 min ago" : `${m} min ago`;
};

export function DoctorScreen() {
  const [doctor, setDoctor] = useState(DOCTORS[0]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [emergencies, setEmergencies] = useState<Emergency[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    if (busyRef.current) return; // don't clobber an in-flight action
    try {
      setError(null);
      const [q, e] = await Promise.all([api.queue(doctor.id), api.emergencies()]);
      setQueue(q);
      setEmergencies(e);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load queue");
    } finally {
      setLoading(false);
    }
  }, [doctor.id]);

  // Live queue: bookings confirmed over WhatsApp/USSD appear on their own,
  // emergencies surface immediately, and closing a visit advances everyone.
  useEffect(() => {
    setLoading(true);
    load();
    const timer = setInterval(load, REFRESH_MS);
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  const close = async (id: string, state: "done" | "follow_up" | "admitted") => {
    setBusy(id);
    busyRef.current = id;
    try {
      await api.closeVisit(id, state);
      busyRef.current = null;
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to close visit");
    } finally {
      busyRef.current = null;
      setBusy(null);
    }
  };

  const acknowledge = async (id: string) => {
    setBusy(id);
    busyRef.current = id;
    try {
      await api.ackEmergency(id);
      busyRef.current = null;
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to acknowledge emergency");
    } finally {
      busyRef.current = null;
      setBusy(null);
    }
  };

  const next = queue.find((q) => q.is_next);
  const rest = queue.filter((q) => !q.is_next);
  const isVirtual = next?.type === "virtual";
  const meetsBy = next?.channel === "whatsapp" ? "video call on WhatsApp" : "phone call";

  return (
    <Board
      role="doctor"
      title="Doctor"
      count={queue.length}
      countLabel="in queue"
      bandExtra={
        <label className="band-field">
          <span className="visually-hidden">Consulting doctor</span>
          <select
            className="band-select"
            value={doctor.id}
            onChange={(e) => setDoctor(DOCTORS.find((d) => d.id === e.target.value) ?? DOCTORS[0])}
          >
            {DOCTORS.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} · {d.specialty}
              </option>
            ))}
          </select>
        </label>
      }
    >
      <p className="context-line">
        <span className="context-date">{todayLong()}</span> — paid bookings from WhatsApp and USSD
        join this queue on their own.
      </p>

      {emergencies.map((e) => (
        <section className="emergency" role="alert" key={e.id}>
          <div className="emergency-head">
            <span className="emergency-tag">Emergency</span>
            <span className="emergency-cat">{e.category}</span>
            <span className="emergency-when">{minutesAgo(e.created_at)}</span>
          </div>
          <p className="emergency-desc">&ldquo;{e.description}&rdquo;</p>
          <div className="emergency-foot">
            <span>
              {e.patient_name}
              {e.patient_phone ? <span className="mono"> · {e.patient_phone}</span> : null}
            </span>
            <button className="btn btn-danger" disabled={busy === e.id} onClick={() => acknowledge(e.id)}>
              Seen — making room
            </button>
          </div>
        </section>
      ))}

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
          No patients in the queue yet. Paid bookings land here the moment they confirm — nothing
          to refresh.
        </div>
      )}

      {!loading && (next || rest.length > 0) && (
        <div className="doctor-grid">
          {next && (
            <section className="ticket" aria-label="Now seeing">
              <div className="ticket-head">
                <span>{isVirtual ? "Now seeing — virtual" : "Now seeing"}</span>
                <span className="ticket-no">No. {ticketNo(next.position)}</span>
              </div>
              <div className="ticket-body">
                <div className="ticket-name">{next.patient_name}</div>
                <div className="ticket-meta">
                  <span>{next.service_name}</span>
                  <span className="meta-dot" role="presentation" />
                  <span className="mono">{timeOf(next.slot_time)}</span>
                  <span className={`chip${isVirtual ? " chip-virtual" : ""}`}>{next.type}</span>
                </div>
                {isVirtual && (
                  <div className="reading">
                    <span className="reading-label">Reported home reading</span>
                    <span className="reading-value">{next.home_reading ?? "None reported"}</span>
                    <span className="reading-how">
                      Meets by {meetsBy}
                      {next.patient_phone ? (
                        <>
                          {" · "}
                          <span className="mono">{next.patient_phone}</span>
                        </>
                      ) : null}
                    </span>
                  </div>
                )}
              </div>
              <div className="ticket-tear" role="presentation" />
              <div className="ticket-actions">
                <button
                  className="btn btn-accent"
                  disabled={busy === next.id}
                  onClick={() => close(next.id, "done")}
                >
                  <IconCheck /> Done
                </button>
                <button
                  className="btn"
                  disabled={busy === next.id}
                  onClick={() => close(next.id, "follow_up")}
                >
                  Follow-up booked
                </button>
                <button
                  className="btn"
                  disabled={busy === next.id}
                  onClick={() => close(next.id, "admitted")}
                >
                  Admitted / procedure
                </button>
              </div>
              <p className="ticket-note">
                Done fires only after consult, meds and the next appointment are settled.
              </p>
            </section>
          )}

          {rest.length > 0 && (
            <section className="panel" aria-label="Up next">
              <div className="panel-head">Up next</div>
              {rest.map((q) => (
                <div className="qrow" key={q.id}>
                  <span className="qrow-no">{ticketNo(q.position)}</span>
                  <span className="qrow-name">{q.patient_name}</span>
                  <span className="qrow-service">{q.service_name}</span>
                  {q.type === "virtual" && <span className="chip chip-virtual">virtual</span>}
                  <span className="qrow-time">{timeOf(q.slot_time)}</span>
                  <span className={`chip chip-${q.status}`}>{q.status.replace("_", " ")}</span>
                </div>
              ))}
            </section>
          )}
        </div>
      )}
    </Board>
  );
}
