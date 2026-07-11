// AI conversation service client.
//
// Aligned to Adam's REAL published contract: POST {AI_SERVICE_URL}/api/v1/ai/interpret
// (backend/app/schemas/ai_service.py). If AI_SERVICE_URL is unset we use a
// deterministic local stub returning the *same* response shape, so the WhatsApp
// conversation is built and testable offline and swaps to the live Gemini
// service by only setting an env var. See docs/contracts/ai-service.md.
import axios from "axios";
import { config } from "./config.js";
import type { Turn } from "./conversation.js";

export type Intent = "book" | "reschedule" | "cancel" | "query" | "unknown";
export type Language = "en" | "pidgin" | "yo";
export type SuggestedAction =
  | "show_services"
  | "show_slots"
  | "confirm_booking"
  | "awaiting_payment"
  | "reschedule"
  | "cancel_booking"
  | "human_handoff"
  | null;

export interface ExtractedEntities {
  service_type: string | null;
  provider_name: string | null;
  preferred_day: string | null;
  preferred_time: string | null;
  patient_name: string | null;
  appointment_id: string | null;
}

export interface AIResponse {
  intent: Intent;
  language: Language;
  entities: ExtractedEntities;
  reply: string;
  confidence: number;
  needs_clarification: boolean;
  suggested_action: SuggestedAction;
}

export interface InterpretInput {
  message: string;
  conversationId: string;
  history: Turn[];
  languageHint?: Language | null;
}

export async function interpret(input: InterpretInput): Promise<AIResponse> {
  if (config.aiServiceUrl) {
    const { data } = await axios.post(
      `${config.aiServiceUrl}/api/v1/ai/interpret`,
      {
        message: input.message,
        channel: "whatsapp",
        conversation_id: input.conversationId,
        history: input.history, // {role, content} — matches ConversationTurn
        language_hint: input.languageHint ?? null,
      },
      { timeout: 20_000 }
    );
    return data as AIResponse;
  }
  return localStub(input.message);
}

export function isLive(): boolean {
  return Boolean(config.aiServiceUrl);
}

// ---- local deterministic stub -------------------------------------------
// Mirrors the live service's response shape and guardrails: it phrases replies
// but never invents a slot, fee, or confirmation. English only; the live Gemini
// service handles Pidgin and Yoruba.

const emptyEntities = (): ExtractedEntities => ({
  service_type: null,
  provider_name: null,
  preferred_day: null,
  preferred_time: null,
  patient_name: null,
  appointment_id: null,
});

const GREET_RE = /\b(hi|hello|hey|howfa|how far|good\s*(morning|afternoon|evening)|start|menu)\b/i;
const BOOK_RE = /\b(book|appointment|see (a )?doctor|consult|register|slot|checkup|check\s?up|test|lab)\b/i;
const CANCEL_RE = /\b(cancel|no longer|can't make|cant make)\b/i;
const RESCHED_RE = /\b(reschedule|change|move|postpone|shift)\b/i;

function detectService(text: string): string | null {
  if (/\b(lab|test|malaria|blood|scan)\b/i.test(text)) return "lab_test";
  if (/\b(follow|virtual|video|online)\b/i.test(text)) return "virtual";
  if (/\b(consult|doctor|checkup|check\s?up|appointment)\b/i.test(text)) return "consultation";
  return null;
}

function localStub(message: string): AIResponse {
  const text = message.trim();
  const base = { language: "en" as Language, entities: emptyEntities(), confidence: 0.85 };

  if (CANCEL_RE.test(text)) {
    return {
      ...base,
      intent: "cancel",
      reply: "No problem — I can help you cancel. What's the name or phone number on the booking?",
      needs_clarification: true,
      suggested_action: "cancel_booking",
    };
  }
  if (RESCHED_RE.test(text)) {
    return {
      ...base,
      intent: "reschedule",
      reply: "Sure, we can move your appointment. Which day and time would suit you better?",
      needs_clarification: true,
      suggested_action: "reschedule",
    };
  }
  if (BOOK_RE.test(text)) {
    const service = detectService(text);
    if (service) {
      return {
        ...base,
        intent: "book",
        entities: { ...emptyEntities(), service_type: service },
        reply: "Great — let's get that booked. What day and time works best for you?",
        needs_clarification: true,
        suggested_action: "show_slots",
      };
    }
    return {
      ...base,
      intent: "book",
      reply:
        "I can help you book 👍 What kind of appointment do you need — a consultation, a lab test, or a follow-up?",
      needs_clarification: true,
      suggested_action: "show_services",
    };
  }
  if (GREET_RE.test(text) || text.length === 0) {
    return {
      ...base,
      intent: "query",
      reply:
        "Hello 👋 Welcome to Automo Health. I can help you book, reschedule, or cancel an appointment. What would you like to do?",
      needs_clarification: true,
      suggested_action: "show_services",
    };
  }
  return {
    ...base,
    intent: "unknown",
    confidence: 0.35,
    reply:
      "Sorry, I didn't quite catch that. Are you trying to book, reschedule, or cancel an appointment?",
    needs_clarification: true,
    suggested_action: null,
  };
}
