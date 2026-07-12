// Thin client for Evolution API v2 (WhatsApp via Baileys).
// Docs: https://doc.evolution-api.com
import axios, { AxiosInstance } from "axios";
import { config } from "./config.js";

const http: AxiosInstance = axios.create({
  baseURL: config.evolutionUrl,
  headers: { apikey: config.evolutionKey, "Content-Type": "application/json" },
  timeout: 20_000,
});

const WEBHOOK_EVENTS = ["MESSAGES_UPSERT", "CONNECTION_UPDATE", "QRCODE_UPDATED"];

export interface QrResult {
  base64?: string; // data URL for the QR image
  code?: string; // raw pairing string
  pairingCode?: string;
}

/** Create the instance if it does not exist. Idempotent-ish: swallows "exists". */
export async function ensureInstance(): Promise<void> {
  try {
    await http.post("/instance/create", {
      instanceName: config.instance,
      integration: "WHATSAPP-BAILEYS",
      qrcode: true,
    });
    console.log("[evolution] instance created:", config.instance);
  } catch (err) {
    const status = axios.isAxiosError(err) ? err.response?.status : undefined;
    const msg = axios.isAxiosError(err) ? JSON.stringify(err.response?.data) : String(err);
    if (status === 403 || status === 409 || /already in use|exists/i.test(msg)) {
      console.log("[evolution] instance already exists:", config.instance);
      return;
    }
    throw err;
  }
}

/** Point the instance's webhook at this service. */
export async function setWebhook(): Promise<void> {
  await http.post(`/webhook/set/${config.instance}`, {
    webhook: {
      enabled: true,
      url: config.webhookUrl,
      webhookByEvents: false,
      webhookBase64: false,
      events: WEBHOOK_EVENTS,
    },
  });
  console.log("[evolution] webhook ->", config.webhookUrl);
}

/** Trigger a connect and return QR / pairing data. Scan it with WhatsApp. */
export async function connect(): Promise<QrResult> {
  const { data } = await http.get(`/instance/connect/${config.instance}`);
  // v2 may return { base64, code, pairingCode } or { qrcode: { base64, code } }
  const qr = data?.qrcode ?? data ?? {};
  return { base64: qr.base64, code: qr.code, pairingCode: qr.pairingCode };
}

export async function connectionState(): Promise<string> {
  const { data } = await http.get(`/instance/connectionState/${config.instance}`);
  return data?.instance?.state ?? data?.state ?? "unknown";
}

/** Send a plain text message. `to` is a bare MSISDN e.g. 2348012345678. */
export async function sendText(to: string, text: string): Promise<void> {
  const number = to.replace(/\D/g, "");
  await http.post(`/message/sendText/${config.instance}`, { number, text });
}
