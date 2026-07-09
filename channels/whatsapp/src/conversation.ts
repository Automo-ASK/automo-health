// Per-thread conversation state. Day 1: in-memory keyed by WhatsApp JID.
// Day 2 hardens this; the real store (Conversation entity) lives in the backend.
import type { ConversationCtx } from "./aiClient.js";

const store = new Map<string, ConversationCtx>();

export function getConversation(jid: string): ConversationCtx {
  let c = store.get(jid);
  if (!c) {
    c = { id: `conv_${jid}`, language: "en", state: {}, history: [] };
    store.set(jid, c);
  }
  return c;
}

export function remember(jid: string, role: "user" | "assistant", text: string): void {
  const c = getConversation(jid);
  c.history.push({ role, text });
  if (c.history.length > 20) c.history.shift(); // short-term memory only
}
