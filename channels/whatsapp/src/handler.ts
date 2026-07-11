// Day-3 WhatsApp booking happy path, on the backend stub:
//   greet -> intent (AI) -> show services -> show open slots -> take a name
//   -> POST /appointments (holds the slot, pending_payment).
//
// Division of labour: the AI service understands the patient and phrases free
// conversation in their language; anything with real data (services, slots,
// fees, holds) is fetched from the booking backend and rendered from the
// localized templates in messages.ts — the AI never invents a slot, fee, or
// confirmation. Payment (link + webhook back into the thread) is Day 4.
import { interpret, isLive, type AIResponse } from "./aiClient.js";
import {
  getConversation,
  appendTurn,
  recentHistory,
  isNewThread,
  resetBooking,
  type ConversationState,
} from "./conversation.js";
import {
  getServices,
  getSlots,
  createAppointment,
  naira,
  SlotUnavailableError,
  type Service,
  type Slot,
} from "./backend.js";
import { t, fmtDay, fmtTime, watDateKey } from "./messages.js";

const MAX_OFFERED_SLOTS = 6;

export async function handleIncoming(jid: string, text: string): Promise<string> {
  const convo = getConversation(jid);
  const firstContact = isNewThread(convo);
  appendTurn(convo, "user", text);

  try {
    return finalize(convo, await route(convo, text, firstContact));
  } catch (err) {
    console.error("[whatsapp] handler error:", err instanceof Error ? err.message : err);
    return finalize(convo, t(convo.language, "backend_down"));
  }
}

async function route(
  convo: ConversationState,
  text: string,
  firstContact: boolean
): Promise<string> {
  const flow = convo.booking;

  // -- Local fast paths: replies to a numbered list, and the name question. --
  // These skip the AI round-trip: a bare "2" or "Chidi Okafor" carries no
  // intent to detect, and the language is already known from earlier turns.
  const choice = parseChoice(text);
  if (choice !== null && flow.stage === "choosing_service") {
    const service = flow.offeredServices[choice - 1];
    return service ? showSlots(convo, service) : t(convo.language, "invalid_choice");
  }
  if (choice !== null && flow.stage === "choosing_slot") {
    const slot = flow.offeredSlots[choice - 1];
    return slot ? slotChosen(convo, slot) : t(convo.language, "invalid_choice");
  }
  if (flow.stage === "awaiting_name" && !looksLikeCommand(text)) {
    flow.patientName = extractName(text);
    return createHold(convo);
  }

  // -- Everything else goes through the AI service. ---------------------------
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
    return "Sorry, I'm having a brief hiccup 🙏 Please send that once more in a moment.";
  }

  convo.language = ai.language;
  console.log(
    `[whatsapp] intent=${ai.intent} lang=${ai.language} action=${ai.suggested_action ?? "-"} ` +
      `stage=${flow.stage} conf=${ai.confidence.toFixed(2)} ${isLive() ? "(live)" : "(stub)"}`
  );

  // Anything the AI picked up in passing sticks — a patient who says
  // "book for my son Tobi tomorrow morning" never gets asked again.
  if (ai.entities.patient_name) flow.patientName = ai.entities.patient_name;

  // Cancelling mid-flow abandons the in-progress booking. Cancelling an
  // existing (paid/confirmed) appointment is a later-day feature — let the AI
  // ask the clarifying questions for now.
  if (ai.intent === "cancel") {
    if (flow.stage !== "idle" && flow.stage !== "held") {
      resetBooking(convo);
      return t(convo.language, "flow_cancelled");
    }
    return ai.reply;
  }

  // A service named in *this* message wins over one picked earlier, so the
  // patient can change their mind at any point ("actually make it a lab test").
  const known = flow.offeredServices.length ? flow.offeredServices : await getServices();
  const switched = matchService(known, ai.entities.service_type, text);

  // We asked for a name and got free text back: maybe the name arrived inside
  // a sentence, maybe they corrected the service, maybe they said something
  // else entirely — the AI has our question in the history, so its reply fits.
  if (flow.stage === "awaiting_name") {
    if (switched && switched.id !== flow.service?.id) return showSlots(convo, switched, prefs(ai));
    if (flow.patientName) return createHold(convo);
    return ai.reply;
  }

  if (ai.intent === "book" || ai.suggested_action === "show_services" || ai.suggested_action === "show_slots") {
    if (flow.stage === "held") resetBooking(convo); // a fresh "book" starts a fresh flow
    const service = switched ?? flow.service;
    if (service) return showSlots(convo, service, prefs(ai));
    return showServices(convo, ai.reply);
  }

  // A free-text reply while a list is showing ("the malaria one", "morning
  // works") that the AI didn't resolve: re-ask rather than lose the patient.
  if (flow.stage === "choosing_service" || flow.stage === "choosing_slot") {
    return ai.needs_clarification && ai.reply ? ai.reply : t(convo.language, "invalid_choice");
  }

  // Greetings, queries, reschedules, handoffs: the AI's own reply.
  return ai.reply;
}

/** Day/time preferences + the AI's phrasing, carried into the slot list. */
function prefs(ai: AIResponse) {
  return {
    date: resolveDate(ai.entities.preferred_day),
    timePref: ai.entities.preferred_time,
    lead: ai.reply,
  };
}

// ---- flow steps -------------------------------------------------------------

async function showServices(convo: ConversationState, lead?: string): Promise<string> {
  const services = await getServices();
  convo.booking.stage = "choosing_service";
  convo.booking.offeredServices = services;
  const lines = services.map((s, i) => `${i + 1}. ${s.name} — ${naira(s.fee)}`);
  // The AI's own phrasing carries the human voice; the list carries the facts.
  const intro = lead ? `${lead}\n\n` : "";
  return `${intro}${t(convo.language, "services_intro")}\n${lines.join("\n")}`;
}

interface SlotPrefs {
  date?: string;
  timePref?: string | null;
  lead?: string;
}

async function showSlots(
  convo: ConversationState,
  service: Service,
  { date, timePref, lead }: SlotPrefs = {}
): Promise<string> {
  const flow = convo.booking;
  flow.service = service;
  let slots = await getSlots(service.id, date);
  if (timePref) {
    // Honour "morning"/"around 10" when possible; never dead-end on it.
    const preferred = slots.filter(matchesTimePref(timePref));
    if (preferred.length > 0) slots = preferred;
  }
  slots = slots.slice(0, MAX_OFFERED_SLOTS);
  if (slots.length === 0) {
    resetBooking(convo);
    return t(convo.language, "no_slots", { service: service.name });
  }
  flow.stage = "choosing_slot";
  flow.offeredSlots = slots;
  const lines = slots.map(
    (s, i) => `${i + 1}. ${fmtDay(s.start_time)}, ${fmtTime(s.start_time)} — ${s.provider_name}`
  );
  const intro = lead ? `${lead}\n\n` : "";
  return `${intro}${t(convo.language, "slots_intro", { service: service.name })}\n${lines.join("\n")}`;
}

async function slotChosen(convo: ConversationState, slot: Slot): Promise<string> {
  const flow = convo.booking;
  flow.chosenSlot = slot;
  if (!flow.patientName) {
    flow.stage = "awaiting_name";
    return t(convo.language, "ask_name");
  }
  return createHold(convo);
}

async function createHold(convo: ConversationState): Promise<string> {
  const flow = convo.booking;
  const { service, chosenSlot, patientName } = flow;
  if (!service || !chosenSlot || !patientName) {
    // Shouldn't happen; restart cleanly rather than crash mid-chat.
    resetBooking(convo);
    return t(convo.language, "invalid_choice");
  }

  let apt;
  try {
    apt = await createAppointment({
      slot_id: chosenSlot.id,
      service_id: service.id,
      type: aptType(service),
      patient: {
        phone: convo.phone,
        name: patientName,
        preferred_language: convo.language,
        preferred_channel: "whatsapp",
        consent: true,
      },
    });
  } catch (err) {
    if (err instanceof SlotUnavailableError) {
      // Race lost: someone took the slot between listing and booking. Re-offer.
      const retry = await showSlots(convo, service);
      if (convo.booking.stage !== "choosing_slot") return retry; // nothing left at all
      return `${t(convo.language, "slot_taken")}\n${retry.split("\n").slice(1).join("\n")}`;
    }
    throw err;
  }

  flow.stage = "held";
  flow.appointmentId = apt.id;
  console.log(`[whatsapp] hold created ${apt.id} slot=${chosenSlot.id} for ${convo.phone}`);
  return t(convo.language, "held", {
    name: patientName.split(" ")[0], // first name, like a person would
    service: service.name,
    doctor: apt.slot?.provider_name ?? chosenSlot.provider_name,
    day: fmtDay(chosenSlot.start_time),
    time: fmtTime(chosenSlot.start_time),
    amount: naira(apt.amount), // one total — the fee split is internal
    expiry: apt.hold_expires_at ? fmtTime(apt.hold_expires_at) : "15 minutes from now",
    ref: apt.id,
  });
}

// ---- small parsers ----------------------------------------------------------

/** "2", "option 2", "no. 2", "2." → 2. Anything else → null. */
function parseChoice(text: string): number | null {
  const m = text.trim().match(/^(?:option|number|no\.?|#)?\s*(\d{1,2})\s*\.?$/i);
  return m ? Number(m[1]) : null;
}

/** Match a service from AI entities or literal text against the offered list. */
function matchService(
  services: Service[],
  serviceType: string | null,
  text: string
): Service | null {
  if (serviceType) {
    const byType = services.find((s) => s.type === serviceType);
    if (byType) return byType;
  }
  const lower = text.toLowerCase();
  return (
    services.find((s) => lower.includes(s.name.toLowerCase())) ??
    services.find((s) =>
      s.type === "consultation"
        ? /\b(consult|doctor|checkup|check\s?up)\b/i.test(text)
        : s.type === "lab_test"
          ? /\b(lab|test|malaria|blood)\b/i.test(text)
          : /\b(follow|virtual|video|online)\b/i.test(text)
    ) ??
    null
  );
}

/** Hour-of-day in WAT, read straight off the +01:00 ISO string. */
function slotHour(s: Slot): number {
  const m = s.start_time.match(/T(\d{2})/);
  return m ? Number(m[1]) : 0;
}

/** "morning" / "afternoon" / "evening" / "10am" / "around 10" → a slot filter. */
function matchesTimePref(pref: string): (s: Slot) => boolean {
  const p = pref.toLowerCase();
  if (/morning|mornin|àárọ̀|aaro/.test(p)) return (s) => slotHour(s) < 12;
  if (/afternoon|ọ̀sán|osan/.test(p)) return (s) => slotHour(s) >= 12 && slotHour(s) < 17;
  if (/evening|night|ìrọ̀lẹ́|irole/.test(p)) return (s) => slotHour(s) >= 17;
  const m = p.match(/(\d{1,2})(?::\d{2})?\s*(am|pm)?/);
  if (m) {
    let h = Number(m[1]);
    if (m[2] === "pm" && h < 12) h += 12;
    return (s) => slotHour(s) === h;
  }
  return () => true;
}

/** "today"/"tomorrow"/ISO date → a slots ?date= filter; anything fuzzier → all days. */
function resolveDate(preferredDay: string | null): string | undefined {
  if (!preferredDay) return undefined;
  const p = preferredDay.trim().toLowerCase();
  if (/^\d{4}-\d{2}-\d{2}$/.test(p)) return p;
  if (/^(today|today today|òní|oni)$/.test(p)) return watDateKey(0);
  if (/^(tomorrow|tomoro|2moro|ọ̀la|ola)$/.test(p)) return watDateKey(1);
  return undefined;
}

/** Words that mean the name-question was dodged and intent should be re-read. */
function looksLikeCommand(text: string): boolean {
  return /\b(cancel|stop|forget|wait|reschedule|change|fagi)\b/i.test(text) || parseChoice(text) !== null;
}

/** Strip "my name is …", "na …", "I'm …" wrappers; keep the name as typed. */
function extractName(text: string): string {
  return (
    text
      .trim()
      .replace(/^(my name (is|na)|i am|i'm|im|na|this is|it's|its|orúkọ mi ni|oruko mi ni)\s+/i, "")
      .replace(/\s+/g, " ")
      .slice(0, 60) || "Patient"
  );
}

function aptType(service: Service): "physical" | "virtual" | "lab" {
  return service.type === "lab_test" ? "lab" : service.type === "virtual" ? "virtual" : "physical";
}

function finalize(convo: ConversationState, reply: string): string {
  appendTurn(convo, "assistant", reply);
  return reply;
}
