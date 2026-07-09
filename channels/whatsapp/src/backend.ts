// Booking backend client (Koded's stub on day 1). See docs/contracts/booking-api.md.
import axios from "axios";
import { config } from "./config.js";

const http = axios.create({ baseURL: config.backendUrl, timeout: 10_000 });

export interface Service {
  id: string;
  type: string;
  name: string;
  fee: number; // kobo
  currency: string;
  duration_minutes: number;
}

export async function getServices(): Promise<Service[]> {
  const { data } = await http.get<Service[]>("/api/v1/services");
  return data;
}

export async function getSlots(serviceId: string, date?: string) {
  const { data } = await http.get("/api/v1/slots", { params: { service_id: serviceId, date } });
  return data as Array<{ id: string; provider_name: string; start_time: string }>;
}

/** ₦ display from kobo. */
export function naira(kobo: number): string {
  return "₦" + (kobo / 100).toLocaleString("en-NG");
}
