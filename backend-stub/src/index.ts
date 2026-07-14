// Day-1 booking backend stub. Implements docs/contracts/booking-api.md with
// in-memory data. Koded's real FastAPI service replaces this at the same paths.
import express, { Request, Response } from "express";
import cors from "cors";
import {
  services,
  providers,
  slots,
  patients,
  appointments,
  payments,
  emergencies,
  nextId,
  dateKey,
  PLATFORM_FEE_KOBO,
  Slot,
  Appointment,
} from "./data.js";

const app = express();
app.use(cors());
app.use(express.json());

const PORT = Number(process.env.PORT ?? 3002);
const HOLD_MINUTES = 15;

const log = (...a: unknown[]) => console.log("[backend-stub]", ...a);

// ---- helpers --------------------------------------------------------------

function providerName(id: string): string {
  return providers.find((p) => p.id === id)?.name ?? "Provider";
}
function serviceName(id: string): string {
  return services.find((s) => s.id === id)?.name ?? "Service";
}
function holdExpiry(): string {
  return new Date(Date.now() + HOLD_MINUTES * 60_000).toISOString();
}
function serializeAppointment(a: Appointment) {
  const slot = slots.find((s) => s.id === a.slot_id);
  return {
    id: a.id,
    status: a.status,
    type: a.type,
    patient_id: a.patient_id,
    slot: slot
      ? { id: slot.id, start_time: slot.start_time, provider_name: providerName(slot.provider_id) }
      : null,
    amount: a.amount,
    consultation_fee: a.consultation_fee,
    platform_fee: a.platform_fee,
    currency: a.currency,
    hold_expires_at: a.hold_expires_at,
  };
}

// Lazily expire stale holds so the calendar never freezes.
function expireStaleHolds() {
  const now = Date.now();
  for (const a of appointments) {
    if (a.status === "pending_payment" && a.hold_expires_at && Date.parse(a.hold_expires_at) < now) {
      a.status = "cancelled";
      const slot = slots.find((s) => s.id === a.slot_id);
      if (slot && slot.status === "held") slot.status = "open";
      const pay = payments.find((p) => p.appointment_id === a.id && p.status === "pending");
      if (pay) pay.status = "expired";
      log("hold expired", a.id);
    }
  }
}

// ---- health ---------------------------------------------------------------

app.get("/health", (_req, res) => res.json({ status: "ok", service: "backend-stub" }));

// ---- services -------------------------------------------------------------

app.get("/api/v1/services", (_req, res) => res.json(services));

// ---- slots ----------------------------------------------------------------

app.get("/api/v1/slots", (req: Request, res: Response) => {
  expireStaleHolds();
  const { service_id, date, include, provider_id } = req.query as Record<string, string>;
  let result = slots.filter((s) => (include === "all" ? true : s.status === "open"));
  if (service_id) result = result.filter((s) => s.service_id === service_id);
  if (provider_id) result = result.filter((s) => s.provider_id === provider_id);
  if (date) result = result.filter((s) => s.start_time.startsWith(date));
  result = [...result].sort((a, b) => a.start_time.localeCompare(b.start_time));
  res.json(result.map(withProviderName));
});

app.get("/api/v1/slots/next", (req: Request, res: Response) => {
  expireStaleHolds();
  const { service_id } = req.query as Record<string, string>;
  const slot = [...slots]
    .filter((s) => s.status === "open" && (!service_id || s.service_id === service_id))
    .sort((a, b) => a.start_time.localeCompare(b.start_time))[0];
  if (!slot) return res.status(404).json({ error: "no_slots" });
  res.json(withProviderName(slot));
});

function withProviderName(s: Slot) {
  return { ...s, provider_name: providerName(s.provider_id) };
}

// ---- appointments ---------------------------------------------------------

app.post("/api/v1/appointments", (req: Request, res: Response) => {
  expireStaleHolds();
  const { slot_id, service_id, type = "physical", channel = "whatsapp", patient } = req.body ?? {};
  const slot = slots.find((s) => s.id === slot_id);
  if (!slot || slot.status !== "open") {
    return res.status(409).json({ error: "slot_unavailable" });
  }

  // upsert patient by phone
  let pat = patients.find((p) => p.phone === patient?.phone);
  if (!pat) {
    pat = {
      id: nextId("pat"),
      phone: patient?.phone ?? "unknown",
      name: patient?.name ?? "Patient",
      preferred_language: patient?.preferred_language ?? "en",
      preferred_channel: patient?.preferred_channel ?? channel,
      consent: Boolean(patient?.consent),
    };
    patients.push(pat);
  }

  slot.status = "held";
  const svc = services.find((s) => s.id === (service_id ?? slot.service_id));
  const fee = svc?.fee ?? 500000;
  const apt: Appointment = {
    id: nextId("apt"),
    patient_id: pat.id,
    slot_id: slot.id,
    service_id: svc?.id ?? slot.service_id,
    type,
    channel,
    status: "pending_payment",
    consultation_fee: fee,
    platform_fee: PLATFORM_FEE_KOBO,
    amount: fee + PLATFORM_FEE_KOBO,
    currency: "NGN",
    hold_expires_at: holdExpiry(),
    created_at: new Date().toISOString(),
  };
  appointments.push(apt);
  log("appointment held", apt.id, "slot", slot.id);
  res.status(201).json(serializeAppointment(apt));
});

// Day summary (cashier screen) — added Day 7, confirm at standup.
// Every appointment on the day across all providers, whatever its state, so
// the cashier sees who came through, who is still expected, and who owes.
// Registered before /appointments/:id so "day" is never read as an id.
app.get("/api/v1/appointments/day", (req: Request, res: Response) => {
  expireStaleHolds();
  const { date } = req.query as Record<string, string>;
  const day = date ?? dateKey(new Date());
  const rows = appointments
    .filter((a) => {
      const slot = slots.find((s) => s.id === a.slot_id);
      return slot && slot.start_time.startsWith(day) && a.status !== "cancelled";
    })
    .map((a) => {
      const slot = slots.find((s) => s.id === a.slot_id)!;
      const pat = patients.find((p) => p.id === a.patient_id);
      return {
        id: a.id,
        patient_name: pat?.name ?? "Patient",
        service_name: serviceName(a.service_id),
        slot_time: slot.start_time,
        type: a.type,
        channel: a.channel,
        status: a.status,
        consultation_fee: a.consultation_fee,
        paid: payments.some((p) => p.appointment_id === a.id && p.status === "paid"),
      };
    })
    .sort((x, y) => x.slot_time.localeCompare(y.slot_time));
  res.json(rows);
});

app.get("/api/v1/appointments/:id", (req, res) => {
  expireStaleHolds();
  const a = appointments.find((x) => x.id === req.params.id);
  if (!a) return res.status(404).json({ error: "not_found" });
  res.json(serializeAppointment(a));
});

// Follow-up booking (doctor action) — added Day 7, confirm at standup.
// Mirrors Koded's real /appointments/{id}/follow-up. Books the next visit
// for the same patient off this one; the notification leg then prompts the
// patient to confirm and pay (PRD 8.3). The next-appointment step sits
// before Done in the close flow.
app.post("/api/v1/appointments/:id/follow-up", (req, res) => {
  expireStaleHolds();
  const parent = appointments.find((x) => x.id === req.params.id);
  if (!parent) return res.status(404).json({ error: "not_found" });
  const { slot_id, service_id } = req.body ?? {};
  const slot = slots.find((s) => s.id === slot_id);
  if (!slot || slot.status !== "open") {
    return res.status(409).json({ error: "slot_unavailable" });
  }
  slot.status = "booked";
  const svc = services.find((s) => s.id === (service_id ?? slot.service_id));
  const fee = svc?.fee ?? 500000;
  const apt: Appointment = {
    id: nextId("apt"),
    patient_id: parent.patient_id,
    slot_id: slot.id,
    service_id: svc?.id ?? slot.service_id,
    type: svc?.type === "virtual" ? "virtual" : svc?.type === "lab_test" ? "lab" : "physical",
    channel: patients.find((p) => p.id === parent.patient_id)?.preferred_channel ?? "whatsapp",
    status: "confirmed",
    consultation_fee: fee,
    platform_fee: PLATFORM_FEE_KOBO,
    amount: fee + PLATFORM_FEE_KOBO,
    currency: "NGN",
    hold_expires_at: null,
    created_at: new Date().toISOString(),
  };
  appointments.push(apt);
  log("follow-up booked", apt.id, "off", parent.id, "-> notify patient to confirm & pay");
  res.status(201).json({
    ...serializeAppointment(apt),
    provider_name: providerName(slot.provider_id),
    service_name: serviceName(apt.service_id),
  });
});

// Cancel (patient action, pre-visit): releases the slot, expires the payment.
// Added Day 3 — channels need this to let a patient correct themselves after a
// hold (change time/name, back out) without waiting for hold-expiry.
app.post("/api/v1/appointments/:id/cancel", (req, res) => {
  const a = appointments.find((x) => x.id === req.params.id);
  if (!a) return res.status(404).json({ error: "not_found" });
  if (["done", "admitted", "in_progress"].includes(a.status)) {
    return res.status(409).json({ error: "already_closed" });
  }
  a.status = "cancelled";
  a.hold_expires_at = null;
  const slot = slots.find((s) => s.id === a.slot_id);
  if (slot && slot.status !== "open") slot.status = "open";
  const pay = payments.find((p) => p.appointment_id === a.id && p.status === "pending");
  if (pay) pay.status = "expired";
  log("appointment cancelled", a.id, "slot released", slot?.id);
  res.json(serializeAppointment(a));
});

// Doctor queue
app.get("/api/v1/appointments", (req: Request, res: Response) => {
  const { date, provider_id } = req.query as Record<string, string>;
  const day = date ?? dateKey(new Date());
  const active: Appointment["status"][] = ["confirmed", "checked_in", "in_progress"];
  let rows = appointments.filter((a) => {
    const slot = slots.find((s) => s.id === a.slot_id);
    if (!slot) return false;
    if (!slot.start_time.startsWith(day)) return false;
    if (provider_id && slot.provider_id !== provider_id) return false;
    return active.includes(a.status);
  });
  rows = rows.sort((a, b) => {
    const sa = slots.find((s) => s.id === a.slot_id)!.start_time;
    const sb = slots.find((s) => s.id === b.slot_id)!.start_time;
    return sa.localeCompare(sb);
  });
  const out = rows.map((a, i) => {
    const slot = slots.find((s) => s.id === a.slot_id)!;
    const pat = patients.find((p) => p.id === a.patient_id);
    return {
      id: a.id,
      position: i + 1,
      is_next: i === 0,
      patient_name: pat?.name ?? "Patient",
      patient_phone: pat?.phone ?? null,
      type: a.type,
      channel: a.channel,
      service_name: serviceName(a.service_id),
      slot_time: slot.start_time,
      status: a.status,
      home_reading: a.home_reading ?? null,
      test_details: a.test_details ?? null,
      collection_date: a.collection_date ?? null,
    };
  });
  res.json(out);
});

// Close a visit (doctor action) — advances the queue.
app.post("/api/v1/appointments/:id/close", (req, res) => {
  const a = appointments.find((x) => x.id === req.params.id);
  if (!a) return res.status(404).json({ error: "not_found" });
  const state = (req.body?.state ?? "done") as string;
  const map: Record<string, Appointment["status"]> = {
    done: "done",
    follow_up: "done",
    admitted: "admitted",
  };
  a.status = map[state] ?? "done";
  // Lab visits: the collection date the patient sees (PRD 9.2). The real
  // service forwards it to the results-ready notification (Adam's leg).
  if (typeof req.body?.collection_date === "string") {
    a.collection_date = req.body.collection_date;
    log("collection date set", a.id, "->", a.collection_date);
  }
  log("appointment closed", a.id, "->", a.status);

  // find new next in the same day/provider
  const slot = slots.find((s) => s.id === a.slot_id);
  const day = slot ? slot.start_time.slice(0, 10) : dateKey(new Date());
  const active: Appointment["status"][] = ["confirmed", "checked_in", "in_progress"];
  const next = appointments
    .filter((x) => {
      const s = slots.find((y) => y.id === x.slot_id);
      return s && s.start_time.startsWith(day) && s.provider_id === slot?.provider_id && active.includes(x.status);
    })
    .sort((x, y) => {
      const sx = slots.find((s) => s.id === x.slot_id)!.start_time;
      const sy = slots.find((s) => s.id === y.slot_id)!.start_time;
      return sx.localeCompare(sy);
    })[0];
  res.json({ ...serializeAppointment(a), next: next ? { id: next.id } : null });
});

// ---- emergencies ----------------------------------------------------------
// PRD 8.6: category plus one sentence, doctor alerted immediately. Added
// Day 7, confirm at standup. Channels create; the doctor board polls and
// acknowledges. Never a replacement for clinical triage.

app.get("/api/v1/emergencies", (req: Request, res: Response) => {
  const { status } = req.query as Record<string, string>;
  const rows = emergencies
    .filter((e) => (status ? e.status === status : true))
    .map((e) => {
      const pat = patients.find((p) => p.id === e.patient_id);
      return { ...e, patient_name: pat?.name ?? "Patient", patient_phone: pat?.phone ?? null };
    })
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  res.json(rows);
});

app.post("/api/v1/emergencies", (req: Request, res: Response) => {
  const { patient, category, description } = req.body ?? {};
  if (!category || !description) {
    return res.status(400).json({ error: "category_and_description_required" });
  }
  let pat = patients.find((p) => p.phone === patient?.phone);
  if (!pat) {
    pat = {
      id: nextId("pat"),
      phone: patient?.phone ?? "unknown",
      name: patient?.name ?? "Patient",
      preferred_language: patient?.preferred_language ?? "en",
      preferred_channel: patient?.preferred_channel ?? "whatsapp",
      consent: Boolean(patient?.consent),
    };
    patients.push(pat);
  }
  const emg = {
    id: nextId("emg"),
    patient_id: pat.id,
    category: String(category),
    description: String(description),
    status: "open" as const,
    created_at: new Date().toISOString(),
  };
  emergencies.push(emg);
  log("emergency raised", emg.id, emg.category);
  res.status(201).json(emg);
});

app.post("/api/v1/emergencies/:id/ack", (req, res) => {
  const e = emergencies.find((x) => x.id === req.params.id);
  if (!e) return res.status(404).json({ error: "not_found" });
  e.status = "acknowledged";
  log("emergency acknowledged", e.id);
  res.json(e);
});

// Make room (doctor action) — added Day 7, confirm at standup. PRD 8.6:
// the scheduled patient is shifted to the nearest available time (Automo
// apologises to them) and the emergency patient is seated now.
app.post("/api/v1/emergencies/:id/make-room", (req, res) => {
  expireStaleHolds();
  const e = emergencies.find((x) => x.id === req.params.id);
  if (!e) return res.status(404).json({ error: "not_found" });
  const providerId = (req.body?.provider_id as string) ?? "prov_ade";
  const day = dateKey(new Date());
  const active: Appointment["status"][] = ["confirmed", "checked_in", "in_progress"];

  // Who is scheduled right now with this provider?
  const queueRows = appointments
    .filter((a) => {
      const s = slots.find((y) => y.id === a.slot_id);
      return s && s.provider_id === providerId && s.start_time.startsWith(day) && active.includes(a.status);
    })
    .sort((x, y) => {
      const sx = slots.find((s) => s.id === x.slot_id)!.start_time;
      const sy = slots.find((s) => s.id === y.slot_id)!.start_time;
      return sx.localeCompare(sy);
    });
  const bumped = queueRows[0];

  // The emergency patient takes the front of the queue.
  let seatSlot: Slot | undefined;
  let bumpedTo: { patient_name: string; new_time: string } | null = null;

  if (bumped) {
    const bumpedSlot = slots.find((s) => s.id === bumped.slot_id)!;
    const nextOpen = slots
      .filter(
        (s) =>
          s.provider_id === providerId &&
          s.status === "open" &&
          s.start_time.startsWith(day) &&
          s.start_time > bumpedSlot.start_time
      )
      .sort((a, b) => a.start_time.localeCompare(b.start_time))[0];
    if (nextOpen) {
      // Shift the scheduled patient; their old slot seats the emergency.
      nextOpen.status = "booked";
      bumped.slot_id = nextOpen.id;
      seatSlot = bumpedSlot;
      const pat = patients.find((p) => p.id === bumped.patient_id);
      bumpedTo = { patient_name: pat?.name ?? "Patient", new_time: nextOpen.start_time };
      log("emergency reshuffle:", pat?.name, "->", nextOpen.start_time, "(apology notification fires)");
    }
  }
  if (!seatSlot) {
    // Nobody to bump (or no room to shift them): take the nearest open slot.
    seatSlot = slots
      .filter((s) => s.provider_id === providerId && s.status === "open" && s.start_time.startsWith(day))
      .sort((a, b) => a.start_time.localeCompare(b.start_time))[0];
    if (seatSlot) seatSlot.status = "booked";
  }
  if (!seatSlot) return res.status(409).json({ error: "no_room_today" });

  const seated: Appointment = {
    id: nextId("apt"),
    patient_id: e.patient_id,
    slot_id: seatSlot.id,
    service_id: "svc_consult",
    type: "physical",
    channel: patients.find((p) => p.id === e.patient_id)?.preferred_channel ?? "whatsapp",
    status: "checked_in",
    consultation_fee: services.find((s) => s.id === "svc_consult")?.fee ?? 500000,
    platform_fee: PLATFORM_FEE_KOBO,
    amount: (services.find((s) => s.id === "svc_consult")?.fee ?? 500000) + PLATFORM_FEE_KOBO,
    currency: "NGN",
    hold_expires_at: null,
    created_at: new Date().toISOString(),
  };
  appointments.push(seated);
  e.status = "acknowledged";
  log("emergency seated", e.id, "as", seated.id, bumpedTo ? `(bumped ${bumpedTo.patient_name})` : "(no bump needed)");
  res.json({ emergency: e, seated: serializeAppointment(seated), bumped_to: bumpedTo });
});

// ---- payments -------------------------------------------------------------

// Cashier's day view: cleared payments for a date. Added Day 6 — the cashier
// screen needs the day's consultation revenue; the facility sees its own money
// (consultation_fee) and the Automo platform fee stays out of the UI.
app.get("/api/v1/payments", (req: Request, res: Response) => {
  const { date } = req.query as Record<string, string>;
  const day = date ?? dateKey(new Date());
  const rows = payments
    .filter((p) => p.status === "paid" && (p.confirmed_at ?? "").startsWith(day))
    .map((p) => {
      const apt = appointments.find((a) => a.id === p.appointment_id);
      const pat = patients.find((x) => x.id === apt?.patient_id);
      return {
        payment_id: p.id,
        appointment_id: p.appointment_id,
        patient_name: pat?.name ?? "Patient",
        service_name: apt ? serviceName(apt.service_id) : "Service",
        method: p.method,
        amount: p.amount,
        consultation_fee: apt?.consultation_fee ?? p.amount,
        platform_fee: apt?.platform_fee ?? 0,
        paid_at: p.confirmed_at,
        channel: apt?.channel ?? "unknown",
      };
    })
    .sort((a, b) => (a.paid_at ?? "").localeCompare(b.paid_at ?? ""));
  res.json(rows);
});

app.post("/api/v1/payments/link", (req, res) => {
  const a = appointments.find((x) => x.id === req.body?.appointment_id);
  if (!a) return res.status(404).json({ error: "appointment_not_found" });
  const ref = Math.random().toString(36).slice(2, 10).toUpperCase();
  const pay = {
    id: nextId("pay"),
    appointment_id: a.id,
    method: "link" as const,
    amount: a.amount,
    currency: "NGN" as const,
    status: "pending" as const,
    url: `https://pay.squadco.com/checkout/${ref}`,
    processor_ref: ref,
    expires_at: a.hold_expires_at ?? holdExpiry(),
  };
  payments.push(pay);
  res.status(201).json({
    payment_id: pay.id,
    method: pay.method,
    url: pay.url,
    amount: pay.amount,
    currency: pay.currency,
    expires_at: pay.expires_at,
  });
});

app.post("/api/v1/payments/virtual-account", (req, res) => {
  const a = appointments.find((x) => x.id === req.body?.appointment_id);
  if (!a) return res.status(404).json({ error: "appointment_not_found" });
  const pat = patients.find((p) => p.id === a.patient_id);
  const acct = "99" + Math.floor(10000000 + Math.random() * 89999999).toString();
  const pay = {
    id: nextId("pay"),
    appointment_id: a.id,
    method: "ussd_transfer" as const,
    amount: a.amount,
    currency: "NGN" as const,
    status: "pending" as const,
    virtual_account: acct,
    bank: "Sterling Bank",
    account_name: `AUTOMO/${(pat?.name ?? "PATIENT").toUpperCase()}`,
    expires_at: a.hold_expires_at ?? holdExpiry(),
  };
  payments.push(pay);
  res.status(201).json({
    payment_id: pay.id,
    method: pay.method,
    virtual_account: pay.virtual_account,
    bank: pay.bank,
    account_name: pay.account_name,
    amount: pay.amount,
    currency: pay.currency,
    expires_at: pay.expires_at,
  });
});

app.get("/api/v1/payments/:id", (req, res) => {
  const p = payments.find((x) => x.id === req.params.id);
  if (!p) return res.status(404).json({ error: "not_found" });
  res.json({ payment_id: p.id, status: p.status, amount: p.amount, method: p.method, appointment_id: p.appointment_id });
});

// Real processor webhook (signature-verified in the real service).
app.post("/api/v1/payments/webhook", (req, res) => {
  const { processor_ref, amount } = req.body ?? {};
  const p = payments.find((x) => x.processor_ref === processor_ref);
  if (!p) return res.status(404).json({ error: "unknown_ref" });
  confirmPayment(p.id, Number(amount), res);
});

// Dev helper: mimic the processor so channels can test end-to-end.
app.post("/api/v1/payments/:id/simulate-webhook", (req, res) => {
  const amount = Number(req.body?.amount);
  confirmPayment(req.params.id, Number.isFinite(amount) ? amount : undefined, res);
});

function confirmPayment(paymentId: string, amount: number | undefined, res: Response) {
  const p = payments.find((x) => x.id === paymentId);
  if (!p) return res.status(404).json({ error: "payment_not_found" });
  const a = appointments.find((x) => x.id === p.appointment_id);
  if (!a) return res.status(404).json({ error: "appointment_not_found" });
  const paid = amount ?? p.amount;
  if (paid < p.amount) {
    return res.status(200).json({ status: "underpaid", expected: p.amount, received: paid, confirmed: false });
  }
  p.status = "paid";
  p.confirmed_at = new Date().toISOString();
  a.status = "confirmed";
  a.hold_expires_at = null;
  const slot = slots.find((s) => s.id === a.slot_id);
  if (slot) slot.status = "booked";
  log("payment confirmed", p.id, "appointment", a.id, amount && amount > p.amount ? "(OVERPAID-flagged)" : "");
  res.json({ status: "paid", confirmed: true, appointment: serializeAppointment(a), overpaid: paid > p.amount });
}

app.listen(PORT, () => {
  log(`listening on http://localhost:${PORT}`);
  log(`${services.length} services, ${slots.length} slots, ${appointments.length} seeded appointments`);
});
