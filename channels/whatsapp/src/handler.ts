// Day-1 message handler. Proves the full loop:
//   Evolution webhook -> AI interpret (stub) -> booking backend (stub) -> reply.
// The real multi-turn booking conversation is days 2–4.
import { interpret } from "./aiClient.js";
import { getConversation, remember } from "./conversation.js";
import { getServices, naira } from "./backend.js";

export async function handleIncoming(jid: string, text: string): Promise<string> {
  const convo = getConversation(jid);
  remember(jid, "user", text);

  const ai = await interpret(text, convo, "whatsapp");
  convo.language = ai.language;

  if (ai.handoff) {
    return reply(jid, "Let me get a member of staff to help you. One moment 🙏");
  }

  // Day 1: for greeting / book / unknown we introduce Automo and list the real
  // services fetched from the backend, so nothing about fees is invented.
  let services;
  try {
    services = await getServices();
  } catch {
    return reply(jid, "Welcome to Automo Health 👋 We're just warming up — please try again in a moment.");
  }

  const menu = services
    .map((s) => `• ${s.name} — ${naira(s.fee)}`)
    .join("\n");

  const lead =
    ai.intent === "book"
      ? "Sure — I can help you book. Here's what we offer:"
      : "Hello 👋 Welcome to Automo Health. Here's what we offer:";

  const body = `${lead}\n\n${menu}\n\nWhich one would you like? (You can just type it — e.g. "consultation tomorrow morning".)`;
  return reply(jid, body);
}

function reply(jid: string, text: string): string {
  remember(jid, "assistant", text);
  return text;
}
