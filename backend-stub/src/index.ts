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
  const { service_id, date, include } = req.query as Record<string, string>;
  let result = slots.filter((s) => (include === "all" ? true : s.status === "open"));
  if (service_id) result = result.filter((s) => s.service_id === service_id);
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

app.get("/api/v1/appointments/:id", (req, res) => {
  expireStaleHolds();
  const a = appointments.find((x) => x.id === req.params.id);
  if (!a) return res.status(404).json({ error: "not_found" });
  res.json(serializeAppointment(a));
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
      type: a.type,
      service_name: serviceName(a.service_id),
      slot_time: slot.start_time,
      status: a.status,
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

// ---- payments -------------------------------------------------------------

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
