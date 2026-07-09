// One-shot WhatsApp provisioning: create the Evolution instance, wire the
// webhook to this service, and print a scannable QR in the terminal.
//
//   npm run provision  (from repo root: npm run provision)
//
// Scan the QR with WhatsApp (Linked devices) to connect the demo number.
import qrcode from "qrcode-terminal";
import { config } from "./config.js";
import { ensureInstance, setWebhook, connect, connectionState } from "./evolution.js";

async function main() {
  console.log(`\nProvisioning Evolution instance "${config.instance}" at ${config.evolutionUrl}`);
  await ensureInstance();
  await setWebhook();
  console.log(`Webhook set to ${config.webhookUrl}\n`);

  const state = await connectionState();
  if (state === "open") {
    console.log("✅ Already connected — no QR needed.");
    return;
  }

  const qr = await connect();
  const raw = qr.code ?? qr.pairingCode;
  if (raw) {
    console.log("Scan this QR in WhatsApp → Linked devices → Link a device:\n");
    qrcode.generate(raw, { small: true });
  } else if (qr.base64) {
    console.log("QR available as base64 (open in a browser):\n");
    console.log(qr.base64.slice(0, 80) + "...");
    console.log("\nOr fetch it live:  GET http://localhost:" + config.port + "/instance/qr");
  } else {
    console.log("No QR returned. Check Evolution logs: npm run evolution:logs");
  }
  console.log("\nAfter scanning, check status:  GET http://localhost:" + config.port + "/instance/state");
}

main().catch((err) => {
  console.error("Provision failed:", (err as any)?.response?.data ?? (err instanceof Error ? err.message : err));
  process.exit(1);
});
