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
  type: string;
  service_name: string;
  slot_time: string;
  status: string;
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

  closeVisit: (id: string, state: "done" | "follow_up" | "admitted") =>
    fetch(`${BASE}/api/v1/appointments/${id}/close`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state }),
    }).then((r) => j<unknown>(r)),

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
