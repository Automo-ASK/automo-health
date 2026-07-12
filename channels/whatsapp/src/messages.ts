// Localized, channel-owned reply templates for the booking flow.
//
// The AI service phrases free conversation (greetings, clarifications) in the
// patient's language, but anything containing real data — services, slots,
// fees, holds — is rendered here from backend responses, so the wording is
// exact and nothing is ever invented. English + Pidgin are the demo pair;
// Yoruba is best-effort pending the Day-6 language polish pass.
import type { Language } from "./aiClient.js";

type Params = Record<string, string | number>;

const templates = {
  services_intro: {
    en: "Here's what we offer — reply with a number:",
    pidgin: "See wetin we get — reply with di number:",
    yo: "Àwọn iṣẹ́ tí a ní nìyí — fi nọ́mbà kan dá wa lóhùn:",
  },
  slots_intro: {
    en: "Next available times for {service} — reply with a number:",
    pidgin: "See di next available time dem for {service} — reply with di number:",
    yo: "Àwọn àkókò tó ṣí sílẹ̀ fún {service} nìyí — fi nọ́mbà kan dá wa lóhùn:",
  },
  no_slots: {
    en: "Sorry, there are no open times for {service} right now 🙏 Please check back a little later.",
    pidgin: "Sorry o, no free time for {service} right now 🙏 Abeg check back small time.",
    yo: "Má bínú, kò sí àkókò tó ṣí sílẹ̀ fún {service} báyìí 🙏 Ẹ tún ṣàyẹ̀wò láìpẹ́.",
  },
  ask_name: {
    en: "Almost done 🙌 What name should I put on the booking?",
    pidgin: "We don almost finish 🙌 Which name I go put for di booking?",
    yo: "Ó fẹ́rẹ̀ parí 🙌 Orúkọ wo ni kí n fi sí ìforúkọsílẹ̀ náà?",
  },
  invalid_choice: {
    en: "Please reply with one of the numbers on the list 🙏",
    pidgin: "Abeg reply with one of di numbers wey dey di list 🙏",
    yo: "Jọ̀wọ́ fi ọ̀kan lára àwọn nọ́mbà orí àkọsílẹ̀ náà dá wa lóhùn 🙏",
  },
  slot_taken: {
    en: "Ah — someone just took that time. Here are the updated times:",
    pidgin: "Ah — person don take dat time. See di ones wey still dey:",
    yo: "Ah — ẹnìkan ṣẹ̀ṣẹ̀ gba àkókò yẹn. Àwọn tó ṣì wà nìyí:",
  },
  // One naira total only — the consultation vs platform-fee split is internal
  // and is never shown to the patient.
  held: {
    en:
      "✅ All set, {name}! Your appointment is reserved.\n\n" +
      "🧾 {service}\n👨‍⚕️ {doctor}\n🗓 {day} at {time}\n💰 {amount}\n\n" +
      "We're holding this spot for you until {expiry}. Your payment link is coming next — payment confirms it. Ref: {ref}",
    pidgin:
      "✅ Correct, {name}! We don reserve am for you.\n\n" +
      "🧾 {service}\n👨‍⚕️ {doctor}\n🗓 {day} by {time}\n💰 {amount}\n\n" +
      "We go hold dis spot for you till {expiry}. Payment link dey come now now — na payment go confirm am. Ref: {ref}",
    yo:
      "✅ Ó ti ṣetán, {name}! A ti fi àyè rẹ pamọ́.\n\n" +
      "🧾 {service}\n👨‍⚕️ {doctor}\n🗓 {day} ní {time}\n💰 {amount}\n\n" +
      "A ó dì àyè yìí mú fún ọ títí di {expiry}. Ìjápọ̀ ìsanwó ń bọ̀ — ìsanwó ni yóò fi ìdí rẹ̀ múlẹ̀. Ref: {ref}",
  },
  updated_intro: {
    en: "Got it — I've updated it ✏️",
    pidgin: "I don update am ✏️",
    yo: "Mo ti ṣàtúnṣe rẹ̀ ✏️",
  },
  hold_cancelled: {
    en: "Done — your booking ({ref}) is cancelled and the time is free again. If you'd like another time, just tell me 🙂",
    pidgin: "Done — I don cancel di booking ({ref}), di time don free again. If you wan another time, just tell me 🙂",
    yo: "Ó parí — a ti fagi lé ìforúkọsílẹ̀ náà ({ref}), àkókò náà ti ṣí sílẹ̀. Tí o bá fẹ́ àkókò mìíràn, sọ fún mi 🙂",
  },
  flow_cancelled: {
    en: "Okay, I've cancelled that booking request. Anything else I can help with?",
    pidgin: "No wahala, I don cancel dat booking. Anything else you need?",
    yo: "Ó dáa, mo ti fagi lé ìbéèrè ìforúkọsílẹ̀ yẹn. Ǹjẹ́ ohun mìíràn wà?",
  },
  backend_down: {
    en: "Sorry, I can't reach our booking system right now 🙏 Please try again in a few minutes.",
    pidgin: "Sorry o, I no fit reach our booking system right now 🙏 Abeg try again in small time.",
    yo: "Má bínú, a kò lè dé ọ̀dọ̀ ètò ìforúkọsílẹ̀ wa báyìí 🙏 Ẹ tún gbìyànjú láìpẹ́.",
  },
} as const;

export type MessageKey = keyof typeof templates;

export function t(lang: string, key: MessageKey, params: Params = {}): string {
  const entry = templates[key];
  const raw = entry[(lang as Language) in entry ? (lang as Language) : "en"] ?? entry.en;
  return raw.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? `{${name}}`));
}

// ---- WAT formatting --------------------------------------------------------
// All backend times carry +01:00; render them in Africa/Lagos regardless of
// host timezone. Day/month names stay English for all languages until the
// Day-6 language polish (Yoruba weekday data is inconsistent across ICU).

const dayFmt = new Intl.DateTimeFormat("en-NG", {
  weekday: "short",
  day: "numeric",
  month: "short",
  timeZone: "Africa/Lagos",
});
const timeFmt = new Intl.DateTimeFormat("en-NG", {
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
  timeZone: "Africa/Lagos",
});

export function fmtDay(iso: string): string {
  return dayFmt.format(new Date(iso));
}

export function fmtTime(iso: string): string {
  return timeFmt.format(new Date(iso)).toUpperCase();
}

/** Today's date key (YYYY-MM-DD) in WAT, offset by `plusDays`. */
export function watDateKey(plusDays = 0): string {
  const d = new Date(Date.now() + plusDays * 86_400_000);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Lagos",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
  return parts; // en-CA gives YYYY-MM-DD
}
