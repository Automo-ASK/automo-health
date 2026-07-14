// Day-4 payment leg of the WhatsApp flow.
//
// After a hold we send the pay link in-chat, then watch for the money two
// ways at once: polling GET /payments/:id (works against the stub and as a
// belt-and-braces fallback), and accepting the backend's notification webhook
// (Koded's reconciliation POSTs {event, data} to NOTIFICATIONS_WEBHOOK_URL —
// point that at POST /webhook/payments here). Whichever lands first wins; the
// channel never decides money arrived on its own — only backend state does.
import { config } from "./config.js";
import { createPaymentLink, getPayment, naira } from "./backend.js";
import {
  getConversation,
  appendTurn,
  resetBooking,
  type ConversationState,
} from "./conversation.js";
import { t, fmtDay, fmtTime } from "./messages.js";

/** How replies leave the building. index.ts wires this to Evolution sendText;
 *  tests wire it to a collector. Keeps this module runnable without WhatsApp. */
type Outbound = (jid: string, text: string) => Promise<void>;
let outbound: Outbound = async (jid) => {
  console.warn(`[payments] outbound not wired; dropping message to ${jid}`);
};
export function setOutbound(fn: Outbound): void {
  outbound = fn;
}

interface Watch {
  appointmentId: string;
  paymentId: string;
  jid: string;
  expiresAt: number; // ms epoch
  timer: ReturnType<typeof setInterval>;
  // Snapshot for the confirmation message — phrased from backend data only.
  summary: { name: string; service: string; doctor: string; startTime: string };
}

const watches = new Map<string, Watch>();

/** Request the pay link for a fresh hold, start watching for the money, and
 *  return the localized in-chat payment instructions. */
export async function beginPaymentWatch(
  convo: ConversationState,
  input: { appointmentId: string; name: string; service: string; doctor: string; startTime: string }
): Promise<string> {
  const link = await createPaymentLink(input.appointmentId);
  stopPaymentWatch(input.appointmentId); // paranoia: never two watches per hold

  const watch: Watch = {
    appointmentId: input.appointmentId,
    paymentId: link.payment_id,
    jid: convo.jid,
    expiresAt: Date.parse(link.expires_at),
    timer: setInterval(() => void poll(input.appointmentId), config.paymentPollMs),
    summary: { name: input.name, service: input.service, doctor: input.doctor, startTime: input.startTime },
  };
  watches.set(input.appointmentId, watch);
  console.log(`[payments] watching ${link.payment_id} for ${input.appointmentId} (${convo.jid})`);

  return t(convo.language, "pay_link", {
    amount: naira(link.amount),
    url: link.url,
    expiry: fmtTime(link.expires_at),
  });
}

/** Stop watching (hold released / corrected / cancelled). Safe to call twice. */
export function stopPaymentWatch(appointmentId: string): void {
  const w = watches.get(appointmentId);
  if (!w) return;
  clearInterval(w.timer);
  watches.delete(appointmentId);
}

/** Immediate status check for "I don pay o" moments: "paid" | "pending". */
export async function checkPaymentNow(appointmentId: string): Promise<"paid" | "pending"> {
  const w = watches.get(appointmentId);
  if (!w) return "paid"; // no watch left = already settled and announced
  const p = await getPayment(w.paymentId);
  if (p.status === "paid") {
    await settle(w, "paid");
    return "paid";
  }
  return "pending";
}

/** Sink for the backend's notification hooks (payment.succeeded,
 *  booking.confirmed, payment.mismatch...). Payloads carry booking/appointment
 *  ids; we only act on holds we are watching. */
export async function onBackendEvent(event: string, data: Record<string, unknown>): Promise<void> {
  const id = String(data?.appointment_id ?? data?.booking_id ?? "");
  if (!id || !watches.has(id)) return;
  if (event === "payment.succeeded" || event === "booking.confirmed") {
    await settle(watches.get(id)!, "paid");
  }
}

// ---- internals --------------------------------------------------------------

async function poll(appointmentId: string): Promise<void> {
  const w = watches.get(appointmentId);
  if (!w) return;
  try {
    const p = await getPayment(w.paymentId);
    if (p.status === "paid") return void (await settle(w, "paid"));
    if (p.status === "expired" || p.status === "failed") return void (await settle(w, "expired"));
  } catch (err) {
    console.error("[payments] poll failed:", err instanceof Error ? err.message : err);
  }
  // Local clock backstop: the stub only expires holds lazily.
  if (Date.now() > w.expiresAt + 60_000) await settle(w, "expired");
}

async function settle(w: Watch, outcome: "paid" | "expired"): Promise<void> {
  stopPaymentWatch(w.appointmentId);
  const convo = getConversation(w.jid);
  const msg =
    outcome === "paid"
      ? t(convo.language, "payment_confirmed", {
          name: w.summary.name.split(" ")[0],
          service: w.summary.service,
          doctor: w.summary.doctor,
          day: fmtDay(w.summary.startTime),
          time: fmtTime(w.summary.startTime),
          ref: w.appointmentId,
        })
      : t(convo.language, "payment_expired", { service: w.summary.service });
  resetBooking(convo); // thread is free for the next thing; name is kept
  appendTurn(convo, "assistant", msg); // the AI sees what we told the patient
  try {
    await outbound(w.jid, msg);
    console.log(`[payments] ${outcome}: ${w.appointmentId} → ${w.jid}`);
  } catch (err) {
    console.error("[payments] send failed:", err instanceof Error ? err.message : err);
  }
}

/** Test seam: inspect/adjust live watches and force a poll tick without waiting. */
export const __test = { watches, poll };
