// Day-2 WhatsApp conversation skeleton.
//   greet -> detect intent (via the AI service) -> send the reply.
//
// The AI service owns understanding + phrasing; it never invents a slot, fee,
// or confirmation. Turning a detected intent into real slots/fees/holds by
// calling the booking backend is Day 3 — the `suggested_action` switch below is
// the seam where that plugs in.
import { interpret, isLive, type AIResponse } from "./aiClient.js";
import {
  getConversation,
  appendTurn,
  recentHistory,
  isNewThread,
  type ConversationState,
} from "./conversation.js";

export async function handleIncoming(jid: string, text: string): Promise<string> {
  const convo = getConversation(jid);
  const firstContact = isNewThread(convo);
  appendTurn(convo, "user", text);

  let ai: AIResponse;
  try {
    ai = await interpret({
      message: text,
      conversationId: convo.id,
      history: recentHistory(convo).slice(0, -1), // context excludes the just-added message
      languageHint: firstContact ? null : (convo.language as AIResponse["language"]),
    });
  } catch (err) {
    // Never leave the patient hanging if the AI layer is slow or down.
    console.error("[whatsapp] AI interpret failed:", err instanceof Error ? err.message : err);
    return finalize(
      convo,
      "Sorry, I'm having a brief hiccup 🙏 Please send that once more in a moment."
    );
  }

  convo.language = ai.language;
  console.log(
    `[whatsapp] intent=${ai.intent} lang=${ai.language} action=${ai.suggested_action ?? "-"} ` +
      `conf=${ai.confidence.toFixed(2)} ${isLive() ? "(live)" : "(stub)"}`
  );

  // Day 3 hook: when the intent needs real data, call the booking backend and
  // let the AI phrase the result. For the Day-2 skeleton we send the AI's reply
  // as-is (it already greets and asks the next question naturally).
  //
  // switch (ai.suggested_action) {
  //   case "show_services": /* fetch services, phrase them */ break;
  //   case "show_slots":    /* fetch open slots, phrase them */ break;
  //   ...
  // }

  return finalize(convo, ai.reply);
}

function finalize(convo: ConversationState, reply: string): string {
  appendTurn(convo, "assistant", reply);
  return reply;
}
