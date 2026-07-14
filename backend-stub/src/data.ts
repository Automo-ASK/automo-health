// In-memory seed data for the Day-1 booking stub.
// WAT (UTC+1). We format times with a fixed +01:00 offset.

export type SlotStatus = "open" | "held" | "booked";
export type AptStatus =
  | "pending_payment"
  | "confirmed"
  | "checked_in"
  | "in_progress"
  | "done"
  | "admitted"
  | "cancelled"
  | "no_show";
export type PaymentStatus = "pending" | "paid" | "failed" | "expired";

export interface Service {
  id: string;
  type: "consultation" | "lab_test" | "virtual";
  name: string;
  fee: number; // kobo
  currency: "NGN";
  duration_minutes: number;
}

export interface Provider {
  id: string;
  name: string;
  role: "doctor" | "lab" | "cashier";
  specialty?: string;
}

export interface Slot {
  id: string;
  provider_id: string;
  service_id: string;
  start_time: string; // ISO with +01:00
  duration_minutes: number;
  status: SlotStatus;
}

export interface Patient {
  id: string;
  phone: string;
  name: string;
  preferred_language: string;
  preferred_channel: string;
  consent: boolean;
}

export interface Appointment {
  id: string;
  patient_id: string;
  slot_id: string;
  service_id: string;
  type: "physical" | "virtual" | "lab";
  channel: string;
  status: AptStatus;
  consultation_fee: number;
  platform_fee: number;
  amount: number;
  currency: "NGN";
  hold_expires_at: string | null;
  created_at: string;
  /** Virtual consults: the home reading the patient reported (PRD 8.4). */
  home_reading?: string;
  /** Lab visits: test details attached before the patient arrives (PRD 9.2). */
  test_details?: string;
  /** Lab visits: collection date the patient sees, set at results-ready. */
  collection_date?: string | null;
}

export interface EmergencyRequest {
  id: string;
  patient_id: string;
  category: string;
  description: string; // one sentence, per the reviewing doctor
  status: "open" | "acknowledged";
  created_at: string;
}

export interface Payment {
  id: string;
  appointment_id: string;
  method: "link" | "ussd_transfer";
  amount: number;
  currency: "NGN";
  status: PaymentStatus;
  virtual_account?: string;
  bank?: string;
  account_name?: string;
  url?: string;
  processor_ref?: string;
  expires_at: string;
  confirmed_at?: string;
}

const PLATFORM_FEE = 10000; // ₦100 flat, kobo

// ---- WAT time helpers -----------------------------------------------------

/** ISO string in WAT (+01:00) for a given date at h:m. */
function watISO(base: Date, h: number, m: number): string {
  const d = new Date(base);
  d.setHours(h, m, 0, 0);
  // Force +01:00 regardless of host tz by building the string manually.
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(
    d.getDate()
  )}T${pad(h)}:${pad(m)}:00+01:00`;
}

export function dateKey(base: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${base.getFullYear()}-${pad(base.getMonth() + 1)}-${pad(
    base.getDate()
  )}`;
}

// ---- Seed -----------------------------------------------------------------

export const services: Service[] = [
  { id: "svc_consult", type: "consultation", name: "General Consultation", fee: 500000, currency: "NGN", duration_minutes: 20 },
  { id: "svc_lab_malaria", type: "lab_test", name: "Malaria Test", fee: 300000, currency: "NGN", duration_minutes: 15 },
  { id: "svc_followup", type: "virtual", name: "Chronic Care Follow-up (Virtual)", fee: 350000, currency: "NGN", duration_minutes: 15 },
];

export const providers: Provider[] = [
  { id: "prov_ade", name: "Dr. Adeyemi", role: "doctor", specialty: "General Practice" },
  { id: "prov_ola", name: "Dr. Olamide", role: "doctor", specialty: "General Practice" },
  { id: "prov_lab", name: "Lab Desk", role: "lab" },
  { id: "prov_cash", name: "Cashier Desk", role: "cashier" },
];

export const slots: Slot[] = [];
export const patients: Patient[] = [];
export const appointments: Appointment[] = [];
export const payments: Payment[] = [];
export const emergencies: EmergencyRequest[] = [];

let seq = 0;
export const nextId = (prefix: string) => `${prefix}_${(++seq).toString().padStart(3, "0")}`;

// Generate open slots for today + next 3 days, for every service:
// consultations 09:00–12:40 per doctor, lab tests 09:00–12:45 at the lab
// desk, virtual follow-ups 14:00–15:45 with Dr. Olamide.
(function seedSlots() {
  const doctors = providers.filter((p) => p.role === "doctor");
  for (let day = 0; day < 4; day++) {
    const base = new Date();
    base.setDate(base.getDate() + day);
    for (const doc of doctors) {
      for (let h = 9; h < 13; h++) {
        for (const m of [0, 20, 40]) {
          slots.push({
            id: nextId("slot"),
            provider_id: doc.id,
            service_id: "svc_consult",
            start_time: watISO(base, h, m),
            duration_minutes: 20,
            status: "open",
          });
        }
      }
    }
    for (let h = 9; h < 13; h++) {
      for (const m of [0, 15, 30, 45]) {
        slots.push({
          id: nextId("slot"),
          provider_id: "prov_lab",
          service_id: "svc_lab_malaria",
          start_time: watISO(base, h, m),
          duration_minutes: 15,
          status: "open",
        });
      }
    }
    for (let h = 14; h < 16; h++) {
      for (const m of [0, 15, 30, 45]) {
        slots.push({
          id: nextId("slot"),
          provider_id: "prov_ola",
          service_id: "svc_followup",
          start_time: watISO(base, h, m),
          duration_minutes: 15,
          status: "open",
        });
      }
    }
  }
})();

// Seed today's queues so every dashboard has something real to show:
// physical + virtual consults for the doctors, tests with details for the
// lab, and a mix of paid / awaiting / seen for the cashier's day view.
(function seedQueue() {
  const today = new Date();

  interface SeedRow {
    name: string;
    phone: string;
    status: AptStatus;
    provider: string;
    service: string;
    type: Appointment["type"];
    channel: string;
    fee: number;
    paid?: boolean; // create a matching cleared payment
    home_reading?: string;
    test_details?: string;
  }

  const rows: SeedRow[] = [
    // Dr. Adeyemi's morning — one already seen, three waiting (one virtual).
    { name: "Chidi Okafor", phone: "2348012345670", status: "done", provider: "prov_ade", service: "svc_consult", type: "physical", channel: "whatsapp", fee: 500000, paid: true },
    { name: "Amina Bello", phone: "2348012345671", status: "checked_in", provider: "prov_ade", service: "svc_consult", type: "physical", channel: "whatsapp", fee: 500000, paid: true },
    { name: "Tunde Balogun", phone: "2348012345672", status: "confirmed", provider: "prov_ade", service: "svc_consult", type: "physical", channel: "ussd", fee: 500000, paid: true },
    {
      name: "Mama Ronke Adesanya", phone: "2348012345673", status: "confirmed", provider: "prov_ade",
      service: "svc_followup", type: "virtual", channel: "whatsapp", fee: 350000, paid: true,
      home_reading: "BP 148/94, taken this morning",
    },
    // Lab desk — tests with details attached before the patient arrives.
    {
      name: "Kunle Afolayan", phone: "2348012345674", status: "confirmed", provider: "prov_lab",
      service: "svc_lab_malaria", type: "lab", channel: "whatsapp", fee: 300000, paid: true,
      test_details: "Malaria (RDT) — ordered by Dr. Adeyemi after yesterday's consult",
    },
    {
      name: "Ngozi Okonkwo", phone: "2348012345675", status: "confirmed", provider: "prov_lab",
      service: "svc_lab_malaria", type: "lab", channel: "sms", fee: 300000, paid: true,
      test_details: "Malaria (RDT) — repeat test, fever persisting after treatment",
    },
    // Still owing: held slot, transfer not landed yet (cashier's "expected").
    { name: "Ibrahim Musa", phone: "2348012345676", status: "pending_payment", provider: "prov_ade", service: "svc_consult", type: "physical", channel: "ussd", fee: 500000 },
  ];

  for (const r of rows) {
    const pat: Patient = {
      id: nextId("pat"),
      phone: r.phone,
      name: r.name,
      preferred_language: "en",
      preferred_channel: r.channel,
      consent: true,
    };
    patients.push(pat);
    const slot = slots.find(
      (s) => s.provider_id === r.provider && s.status === "open" && s.start_time.startsWith(dateKey(today))
    );
    if (slot) slot.status = r.status === "pending_payment" ? "held" : "booked";
    const apt: Appointment = {
      id: nextId("apt"),
      patient_id: pat.id,
      slot_id: slot ? slot.id : "",
      service_id: r.service,
      type: r.type,
      channel: r.channel,
      status: r.status,
      consultation_fee: r.fee,
      platform_fee: PLATFORM_FEE,
      amount: r.fee + PLATFORM_FEE,
      currency: "NGN",
      hold_expires_at: r.status === "pending_payment" ? new Date(Date.now() + 15 * 60_000).toISOString() : null,
      created_at: new Date().toISOString(),
      home_reading: r.home_reading,
      test_details: r.test_details,
      collection_date: null,
    };
    appointments.push(apt);
    if (r.paid) {
      payments.push({
        id: nextId("pay"),
        appointment_id: apt.id,
        method: r.channel === "whatsapp" ? "link" : "ussd_transfer",
        amount: apt.amount,
        currency: "NGN",
        status: "paid",
        processor_ref: `SEED${apt.id}`,
        expires_at: new Date().toISOString(),
        confirmed_at: new Date().toISOString(),
      });
    }
  }

  // One open emergency so the doctor's alert surface is live (PRD 8.6):
  // category plus one sentence, never free-text alone.
  emergencies.push({
    id: nextId("emg"),
    patient_id: patients[patients.length - 1].id,
    category: "Chest pain / breathing difficulty",
    description: "My father is having chest pain and struggling to breathe.",
    status: "open",
    created_at: new Date(Date.now() - 4 * 60_000).toISOString(),
  });
})();

export const PLATFORM_FEE_KOBO = PLATFORM_FEE;
