// AI conversation service client. If AI_SERVICE_URL is set, proxy to Adam's
// real service (docs/contracts/ai-service.md). Otherwise use a deterministic
// local stub so the WhatsApp flow can be built on day 1 before the model exists.
import axios from "axios";
import { config } from "./config.js";

export type Intent = "book" | "reschedule" | "cancel" | "question" | "greeting" | "unknown";

export interface Interpretation {
  language: string;
  intent: Intent;
  confidence: number;
  entities: Record<string, string | null>;
  missing: string[];
  reply: string;
  needs_backend: boolean;
  handoff: boolean;
}

export interface ConversationCtx {
  id: string;
  language: string;
  state: Record<string, unknown>;
  history: Array<{ role: "user" | "assistant"; text: string }>;
}

export async function interpret(
  message: string,
  conversation: ConversationCtx | null,
  channel = "whatsapp"
): Promise<Interpretation> {
  if (config.aiServiceUrl) {
    const { data } = await axios.post(
      `${config.aiServiceUrl}/ai/v1/interpret`,
      { channel, message, conversation },
      { timeout: 15_000 }
    );
    return data as Interpretation;
  }
  return localStub(message);
}

// ---- local deterministic stub (days 1–2) ----------------------------------

const BOOK_RE = /\b(book|appointment|see (a )?doctor|consult|register|slot|checkup|check up)\b/i;
const GREET_RE = /\b(hi|hello|hey|good (morning|afternoon|evening)|start|menu)\b/i;

function localStub(message: string): Interpretation {
  const text = message.trim();
  if (BOOK_RE.test(text)) {
    return {
      language: "en",
      intent: "book",
      confidence: 0.9,
      entities: { service: null, provider: null, preferred_day: null, preferred_time: null, patient_name: null },
      missing: ["service"],
      reply: "",
      needs_backend: true, // channel will fetch real services/slots and phrase them
      handoff: false,
    };
  }
  if (GREET_RE.test(text) || text.length === 0) {
    return {
      language: "en",
      intent: "greeting",
      confidence: 0.8,
      entities: {},
      missing: [],
      reply: "",
      needs_backend: true,
      handoff: false,
    };
  }
  return {
    language: "en",
    intent: "unknown",
    confidence: 0.3,
    entities: {},
    missing: [],
    reply: "",
    needs_backend: true,
    handoff: false,
  };
}
