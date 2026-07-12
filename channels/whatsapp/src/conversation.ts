// Per-thread conversation state for WhatsApp.
//
// Day 2: in-memory, keyed by WhatsApp JID. Shape mirrors Adam's backend
// Conversation entity (history as {role, content} turns, language, timestamps)
// so a later swap to the shared store is mechanical. WhatsApp is stateful across
// messages: the patient never has to repeat themselves.
import { config } from "./config.js";
import type { Service, Slot } from "./backend.js";

export type Role = "user" | "assistant";

export interface Turn {
  role: Role;
  content: string;
}

// Where the patient is in the booking happy path. The numbered lists we last
// showed are kept so a bare "2" reply resolves without a round-trip to the AI.
export type BookingStage =
  | "idle"
  | "choosing_service"
  | "choosing_slot"
  | "awaiting_name"
  | "held";

export interface BookingFlow {
  stage: BookingStage;
  service: Service | null;
  offeredSlots: Slot[];
  chosenSlot: Slot | null;
  patientName: string | null;
  appointmentId: string | null;
  offeredServices: Service[];
}

export interface ConversationState {
  id: string; // stable per thread; becomes the backend conversation_id later
  jid: string; // full WhatsApp JID, e.g. 2348012345678@s.whatsapp.net
  phone: string; // bare MSISDN
  language: string; // last detected language (en | pidgin | yo)
  history: Turn[]; // full short-term memory (capped)
  booking: BookingFlow;
  lastMessageAt: string | null;
}

export function freshBooking(): BookingFlow {
  return {
    stage: "idle",
    service: null,
    offeredServices: [],
    offeredSlots: [],
    chosenSlot: null,
    patientName: null,
    appointmentId: null,
  };
}

/** Reset the flow but remember the patient's name for their next booking. */
export function resetBooking(c: ConversationState): void {
  const name = c.booking.patientName;
  c.booking = { ...freshBooking(), patientName: name };
}

const store = new Map<string, ConversationState>();

export function getConversation(jid: string): ConversationState {
  let c = store.get(jid);
  if (!c) {
    c = {
      id: `wa_${jid.split("@")[0]}`,
      jid,
      phone: jid.split("@")[0],
      language: "en",
      history: [],
      booking: freshBooking(),
      lastMessageAt: null,
    };
    store.set(jid, c);
  }
  return c;
}

export function isNewThread(c: ConversationState): boolean {
  return c.history.length === 0;
}

export function appendTurn(c: ConversationState, role: Role, content: string): void {
  c.history.push({ role, content });
  c.lastMessageAt = new Date().toISOString();
  // Keep only short-term memory on the wire; storage cap is a bit larger.
  const maxStored = config.aiMaxHistoryTurns * 2;
  if (c.history.length > maxStored) {
    c.history.splice(0, c.history.length - maxStored);
  }
}

/** The most recent turns to send to the AI service as context. */
export function recentHistory(c: ConversationState): Turn[] {
  return c.history.slice(-config.aiMaxHistoryTurns);
}
