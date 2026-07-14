// Booking API client for the dashboards. Talks to /api/v1 (proxied to the
// stub in dev; set VITE_API_URL to hit Koded's real service directly).
// Matches docs/contracts/booking-api.md.

const BASE: string = import.meta.env?.VITE_API_URL?.replace(/\/$/, "") ?? "";

export interface PaymentRow {
  payment_id: string;
  appointment_id: string;
  patient_name: string;
  service_name: string;
  method: string;
  amount: number;
  consultation_fee: number;
  platform_fee: number;
  paid_at: string | null;
  channel: string;
}

export interface QueueItem {
  id: string;
  position: number;
  is_next: boolean;
  patient_name: string;
  patient_phone: string | null;
  type: string;
  channel: string;
  service_name: string;
  slot_time: string;
  status: string;
  /** Virtual consults: the home reading the patient reported. */
  home_reading: string | null;
  /** Lab visits: test details attached before the patient arrives. */
  test_details: string | null;
  collection_date: string | null;
}

export interface DayRow {
  id: string;
  patient_name: string;
  service_name: string;
  slot_time: string;
  type: string;
  channel: string;
  status: string;
  consultation_fee: number;
  paid: boolean;
}

export interface Emergency {
  id: string;
  patient_name: string;
  patient_phone: string | null;
  category: string;
  description: string;
  status: "open" | "acknowledged";
  created_at: string;
}

export interface Slot {
  id: string;
  provider_id: string;
  provider_name: string;
  service_id: string;
  start_time: string;
  duration_minutes: number;
  status: "open" | "held" | "booked";
}

export interface MakeRoomResult {
  bumped_to: { patient_name: string; new_time: string } | null;
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${BASE}/health`).then((r) => j<{ status: string }>(r)),

  queue: (providerId = "prov_ade") =>
    fetch(`${BASE}/api/v1/appointments?provider_id=${encodeURIComponent(providerId)}`).then((r) =>
      j<QueueItem[]>(r)
    ),

  closeVisit: (id: string, state: "done" | "follow_up" | "admitted", collectionDate?: string) =>
    fetch(`${BASE}/api/v1/appointments/${id}/close`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectionDate ? { state, collection_date: collectionDate } : { state }),
    }).then((r) => j<unknown>(r)),

  /** Every appointment on the day, all providers, all states — cashier view. */
  day: (date?: string) =>
    fetch(`${BASE}/api/v1/appointments/day${date ? `?date=${encodeURIComponent(date)}` : ""}`).then(
      (r) => j<DayRow[]>(r)
    ),

  emergencies: () =>
    fetch(`${BASE}/api/v1/emergencies?status=open`).then((r) => j<Emergency[]>(r)),

  ackEmergency: (id: string) =>
    fetch(`${BASE}/api/v1/emergencies/${id}/ack`, { method: "POST" }).then((r) => j<unknown>(r)),

  /** Seat the emergency patient now; the backend shifts whoever was scheduled. */
  makeRoom: (id: string, providerId: string) =>
    fetch(`${BASE}/api/v1/emergencies/${id}/make-room`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider_id: providerId }),
    }).then((r) => j<MakeRoomResult>(r)),

  slots: (opts: { service_id?: string; provider_id?: string; date?: string; include?: "all" } = {}) => {
    const q = new URLSearchParams();
    if (opts.service_id) q.set("service_id", opts.service_id);
    if (opts.provider_id) q.set("provider_id", opts.provider_id);
    if (opts.date) q.set("date", opts.date);
    if (opts.include) q.set("include", opts.include);
    const qs = q.toString();
    return fetch(`${BASE}/api/v1/slots${qs ? `?${qs}` : ""}`).then((r) => j<Slot[]>(r));
  },

  /** Book the patient's next visit off this appointment (doctor action). */
  followUp: (id: string, slotId: string, serviceId?: string) =>
    fetch(`${BASE}/api/v1/appointments/${id}/follow-up`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(serviceId ? { slot_id: slotId, service_id: serviceId } : { slot_id: slotId }),
    }).then((r) => j<{ id: string; provider_name: string; service_name: string }>(r)),

  services: () =>
    fetch(`${BASE}/api/v1/services`).then((r) =>
      j<Array<{ id: string; name: string; fee: number; type: string }>>(r)
    ),

  /** Cleared payments for a date (default today) — the cashier's day view. */
  payments: (date?: string) =>
    fetch(`${BASE}/api/v1/payments${date ? `?date=${encodeURIComponent(date)}` : ""}`).then((r) =>
      j<PaymentRow[]>(r)
    ),
};

export const naira = (kobo: number) => "₦" + (kobo / 100).toLocaleString("en-NG");

export const timeOf = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-NG", { hour: "2-digit", minute: "2-digit", hour12: true });
