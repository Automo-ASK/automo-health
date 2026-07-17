// Standalone QR display: run this directly in your own terminal (the QR
// doesn't render reliably through other UIs). Keeps fetching a fresh QR and
// checking connection state until you've scanned it, since Evolution's QR
// codes expire after a short while.
//
//   npm run qr   (from repo root, or: npm run qr -w channels/whatsapp)
import qrcode from "qrcode-terminal";
import { ensureInstance, setWebhook, connect, connectionState } from "./evolution.js";
import { config } from "./config.js";

const POLL_MS = 30_000;
const MAX_ATTEMPTS = 45; // ~3 minutes

async function main() {
  console.log(`Provisioning Evolution instance "${config.instance}" at ${config.evolutionUrl}`);
  await ensureInstance();
  await setWebhook();

  for (let i = 0; i < MAX_ATTEMPTS; i++) {
    const state = await connectionState();
    if (state === "open") {
      console.log("\n✅ Connected! Your WhatsApp is linked.");
      console.log("Send a message to that number from another phone to test the booking flow.");
      return;
    }

    const qr = await connect();
    const raw = qr.code ?? qr.pairingCode;
    console.clear();
    console.log(`Instance: ${config.instance}   State: ${state}   (attempt ${i + 1}/${MAX_ATTEMPTS})\n`);
    if (raw) {
      console.log("Scan this QR in WhatsApp → Linked devices → Link a device:\n");
      qrcode.generate(raw, { small: true });
    } else {
      console.log("No QR yet — retrying...");
    }
    console.log(`\nRefreshing in ${POLL_MS / 1000}s. Ctrl+C to stop once connected.`);
    await new Promise((r) => setTimeout(r, POLL_MS));
  }

  console.log("\nGave up waiting for a connection. Re-run this script to try again.");
}

main().catch((err) => {
  console.error("QR display failed:", (err as any)?.response?.data ?? (err instanceof Error ? err.message : err));
  process.exit(1);
});
