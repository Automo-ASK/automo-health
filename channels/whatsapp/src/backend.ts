// Booking backend client (Koded's stub on day 1). See docs/contracts/booking-api.md.
import axios from "axios";
import { config } from "./config.js";

const http = axios.create({ baseURL: config.backendUrl, timeout: 10_000 });

export interface Service {
  id: string;
  type: "consultation" | "lab_test" | "virtual";
  name: string;
  fee: number; // kobo
  currency: string;
  duration_minutes: number;
}

export interface Slot {
  id: string;
  provider_id: string;
  provider_name: string;
  service_id: string;
  start_time: string; // ISO, +01:00
  duration_minutes: number;
  status: "open" | "held" | "booked";
}

export interface AppointmentHold {
  id: string;
  status: string;
  type: string;
  patient_id: string;
  slot: { id: string; start_time: string; provider_name: string } | null;
  amount: number; // kobo, consultation + platform fee
  consultation_fee: number;
  platform_fee: number;
  currency: string;
  hold_expires_at: string | null;
}

export interface PatientInput {
  phone: string;
  name: string;
  preferred_language: string;
  preferred_channel: string;
  consent: boolean;
}

/** The slot was taken (or the hold expired) between showing it and booking it. */
export class SlotUnavailableError extends Error {
  constructor() {
    super("slot_unavailable");
    this.name = "SlotUnavailableError";
  }
}

export async function getServices(): Promise<Service[]> {
  const { data } = await http.get<Service[]>("/api/v1/services");
  return data;
}

export async function getSlots(serviceId: string, date?: string): Promise<Slot[]> {
  const { data } = await http.get<Slot[]>("/api/v1/slots", {
    params: { service_id: serviceId, date },
  });
  return data;
}

/** Creates the appointment as pending_payment and holds the slot exclusively. */
export async function createAppointment(input: {
  slot_id: string;
  service_id: string;
  type: "physical" | "virtual" | "lab";
  patient: PatientInput;
}): Promise<AppointmentHold> {
  try {
    const { data } = await http.post<AppointmentHold>("/api/v1/appointments", {
      ...input,
      channel: "whatsapp",
    });
    return data;
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.status === 409) {
      throw new SlotUnavailableError();
    }
    throw err;
  }
}

/** ₦ display from kobo. */
export function naira(kobo: number): string {
  return "₦" + (kobo / 100).toLocaleString("en-NG");
}
