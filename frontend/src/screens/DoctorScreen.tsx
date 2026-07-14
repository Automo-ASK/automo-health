import { useEffect, useState, useCallback, useRef } from "react";
import { api, timeOf, type QueueItem, type Emergency, type Slot } from "../api";
import { Board, todayLong, ticketNo } from "../Board";
import { IconCheck } from "../icons";

const DOCTORS = [
  { id: "prov_ade", name: "Dr. Adeyemi", specialty: "General Practice" },
  { id: "prov_ola", name: "Dr. Olamide", specialty: "General Practice" },
];

const FOLLOW_UP_SERVICES = [
  { id: "svc_consult", label: "In person" },
  { id: "svc_followup", label: "Virtual (chronic care)" },
];

const REFRESH_MS = 5000;

const pad = (n: number) => String(n).padStart(2, "0");

const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

function daysFromNow(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return ymd(d);
}

const prettyDate = (dateStr: string) =>
  new Date(`${dateStr}T12:00:00`).toLocaleDateString("en-NG", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

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
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const busyRef = useRef<string | null>(null);

  // Availability: how free am I on a given day?
  const [availDate, setAvailDate] = useState(ymd(new Date()));
  const [avail, setAvail] = useState<Slot[]>([]);

  // Follow-up picker state.
  const [fuOpen, setFuOpen] = useState(false);
  const [fuService, setFuService] = useState(FOLLOW_UP_SERVICES[0].id);
  const [fuDate, setFuDate] = useState(daysFromNow(1));
  const [fuSlots, setFuSlots] = useState<Slot[]>([]);
  const [fuLoading, setFuLoading] = useState(false);

  const load = useCallback(async () => {
    if (busyRef.current) return; // don't clobber an in-flight action
    try {
      setError(null);
      const [q, e, av] = await Promise.all([
        api.queue(doctor.id),
        api.emergencies(),
        api.slots({ provider_id: doctor.id, date: availDate, include: "all" }),
      ]);
      setQueue(q);
      setEmergencies(e);
      setAvail(av);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load queue");
    } finally {
      setLoading(false);
    }
  }, [doctor.id, availDate]);

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

  const next = queue.find((q) => q.is_next);
  const rest = queue.filter((q) => !q.is_next);
  const isVirtual = next?.type === "virtual";
  const meetsBy = next?.channel === "whatsapp" ? "video call on WhatsApp" : "phone call";

  // A new patient in the chair means any half-open picker is stale.
  const nextId = next?.id;
  useEffect(() => {
    setFuOpen(false);
  }, [nextId, doctor.id]);

  // Fetch open slots for the follow-up picker whenever it's open.
  useEffect(() => {
    if (!fuOpen) return;
    let stale = false;
    setFuLoading(true);
    api
      .slots({ service_id: fuService, date: fuDate })
      .then((s) => {
        if (!stale) setFuSlots(s);
      })
      .catch(() => {
        if (!stale) setFuSlots([]);
      })
      .finally(() => {
        if (!stale) setFuLoading(false);
      });
    return () => {
      stale = true;
    };
  }, [fuOpen, fuService, fuDate]);

  const withBusy = async (key: string, fn: () => Promise<void>, failMsg: string) => {
    setBusy(key);
    busyRef.current = key;
    try {
      await fn();
      busyRef.current = null;
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : failMsg);
    } finally {
      busyRef.current = null;
      setBusy(null);
    }
  };

  const close = (id: string, state: "done" | "follow_up" | "admitted") =>
    withBusy(id, async () => {
      await api.closeVisit(id, state);
      setInfo(null);
    }, "Failed to close visit");

  const bookFollowUp = (slot: Slot) => {
    if (!next) return;
    const patient = next.patient_name;
    return withBusy(next.id, async () => {
      const booked = await api.followUp(next.id, slot.id, fuService);
      await api.closeVisit(next.id, "follow_up");
      setFuOpen(false);
      setInfo(
        `Follow-up booked for ${patient}: ${prettyDate(fuDate)}, ${timeOf(slot.start_time)} with ${
          booked.provider_name
        }. The patient will be prompted to confirm and pay.`
      );
    }, "Failed to book follow-up");
  };

  const makeRoom = (e: Emergency) =>
    withBusy(e.id, async () => {
      const r = await api.makeRoom(e.id, doctor.id);
      setInfo(
        r.bumped_to
          ? `${e.patient_name} is seated next. ${r.bumped_to.patient_name} was shifted to ${timeOf(
              r.bumped_to.new_time
            )} — the apology and new time go out automatically.`
          : `${e.patient_name} is seated next — no one needed to move.`
      );
    }, "Failed to make room");

  const acknowledge = (id: string) =>
    withBusy(id, async () => {
      await api.ackEmergency(id);
    }, "Failed to acknowledge emergency");

  const openSlots = avail.filter((s) => s.status === "open").length;

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
            <span className="emergency-actions">
              <button className="btn btn-danger" disabled={busy === e.id} onClick={() => makeRoom(e)}>
                Make room — seat them next
              </button>
              <button className="btn" disabled={busy === e.id} onClick={() => acknowledge(e.id)}>
                Handled outside
              </button>
            </span>
          </div>
        </section>
      ))}

      {info && (
        <div className="banner-ok" role="status">
          <span>{info}</span>
          <button className="banner-ok-dismiss" onClick={() => setInfo(null)} aria-label="Dismiss">
            Dismiss
          </button>
        </div>
      )}

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

      {!loading && (
        <div className="doctor-grid">
          <div className="doctor-col">
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
                {!fuOpen ? (
                  <>
                    <div className="ticket-actions">
                      <button
                        className="btn btn-accent"
                        disabled={busy === next.id}
                        onClick={() => close(next.id, "done")}
                      >
                        <IconCheck /> Done
                      </button>
                      <button className="btn" disabled={busy === next.id} onClick={() => setFuOpen(true)}>
                        Book follow-up
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
                  </>
                ) : (
                  <div className="fu">
                    <div className="fu-controls">
                      <div className="fu-field">
                        <span className="fu-label">Visit type</span>
                        <span className="fu-toggle" role="group" aria-label="Follow-up type">
                          {FOLLOW_UP_SERVICES.map((s) => (
                            <button
                              key={s.id}
                              className={`btn btn-row${fuService === s.id ? " btn-accent" : ""}`}
                              aria-pressed={fuService === s.id}
                              onClick={() => setFuService(s.id)}
                            >
                              {s.label}
                            </button>
                          ))}
                        </span>
                      </div>
                      <label className="fu-field">
                        <span className="fu-label">Date</span>
                        <input
                          type="date"
                          className="date-input"
                          value={fuDate}
                          min={daysFromNow(0)}
                          onChange={(e) => setFuDate(e.target.value)}
                        />
                      </label>
                      <button className="btn" onClick={() => setFuOpen(false)}>
                        Back
                      </button>
                    </div>
                    {fuLoading && <p className="fu-hint">Checking open slots…</p>}
                    {!fuLoading && fuSlots.length === 0 && (
                      <p className="fu-hint">No open slots that day — try another date.</p>
                    )}
                    {!fuLoading && fuSlots.length > 0 && (
                      <div className="fu-slots">
                        {fuSlots.slice(0, 12).map((s) => (
                          <button
                            key={s.id}
                            className="slot-chip"
                            disabled={busy === next.id}
                            onClick={() => bookFollowUp(s)}
                          >
                            <span className="slot-chip-time">{timeOf(s.start_time)}</span>
                            <span className="slot-chip-provider">{s.provider_name}</span>
                          </button>
                        ))}
                      </div>
                    )}
                    <p className="fu-hint">
                      Picking a slot books it and closes this visit as follow-up booked.
                    </p>
                  </div>
                )}
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

          <section className="panel avail" aria-label="Availability">
            <div className="panel-head">
              <span>How free am I</span>
            </div>
            <div className="avail-body">
              <div className="avail-controls">
                <label className="fu-field">
                  <span className="visually-hidden">Day to check</span>
                  <input
                    type="date"
                    className="date-input"
                    value={availDate}
                    onChange={(e) => setAvailDate(e.target.value)}
                  />
                </label>
                <span className="avail-summary">
                  <span className="avail-count">{openSlots}</span> of {avail.length} slots open
                </span>
              </div>
              {avail.length === 0 ? (
                <p className="fu-hint">No slots set up for this day.</p>
              ) : (
                <div className="avail-grid">
                  {avail.map((s) => (
                    <span key={s.id} className={`avail-chip avail-${s.status}`} title={s.status}>
                      {timeOf(s.start_time).replace(/\s/g, "")}
                    </span>
                  ))}
                </div>
              )}
              <p className="fu-hint">Open slots are what patients can book right now.</p>
            </div>
          </section>
        </div>
      )}
    </Board>
  );
}
