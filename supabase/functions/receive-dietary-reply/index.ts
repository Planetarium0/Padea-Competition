import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const SENDGRID_INBOUND_VERIFICATION_KEY = Deno.env.get("SENDGRID_INBOUND_VERIFICATION_KEY") ?? "";
const APP_DOMAIN = Deno.env.get("APP_DOMAIN") ?? "";

// ECDSA P-256 signature verification for the SendGrid webhook.
// Signature header: X-Twilio-Email-Event-Webhook-Signature (base64url)
// Timestamp header: X-Twilio-Email-Event-Webhook-Timestamp
// Signed message: timestamp + body
async function verifySignature(
  publicKeyPem: string,
  signature: string,
  timestamp: string,
  body: string,
): Promise<boolean> {
  try {
    const pemContent = publicKeyPem
      .replace(/-----BEGIN PUBLIC KEY-----/, "")
      .replace(/-----END PUBLIC KEY-----/, "")
      .replace(/\s/g, "");
    const keyData = Uint8Array.from(atob(pemContent), (c) => c.charCodeAt(0));
    const key = await crypto.subtle.importKey(
      "spki",
      keyData.buffer,
      { name: "ECDSA", namedCurve: "P-256" },
      false,
      ["verify"],
    );
    // base64url → bytes
    const sigPadded = signature.replace(/-/g, "+").replace(/_/g, "/");
    const sigBytes = Uint8Array.from(atob(sigPadded), (c) => c.charCodeAt(0));
    const message = new TextEncoder().encode(timestamp + body);
    return await crypto.subtle.verify(
      { name: "ECDSA", hash: "SHA-256" },
      key,
      sigBytes,
      message,
    );
  } catch {
    return false;
  }
}

function extractRequestCode(toAddress: string): string | null {
  const local = toAddress.split("@")[0] ?? "";
  if (!local.startsWith("dietary-")) return null;
  const code = local.slice("dietary-".length);
  return code || null;
}

function parseHeadersString(headersStr: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of headersStr.split("\n")) {
    const colonIdx = line.indexOf(":");
    if (colonIdx === -1) continue;
    const key = line.slice(0, colonIdx).trim().toLowerCase();
    const val = line.slice(colonIdx + 1).trim();
    result[key] = val;
  }
  return result;
}

Deno.serve(async (req: Request) => {
  const bodyText = await req.text();

  // Signature verification (skip if no key configured)
  if (SENDGRID_INBOUND_VERIFICATION_KEY) {
    const sig = req.headers.get("X-Twilio-Email-Event-Webhook-Signature") ?? "";
    const ts  = req.headers.get("X-Twilio-Email-Event-Webhook-Timestamp") ?? "";
    if (!sig || !ts) {
      return new Response("Missing signature headers", { status: 403 });
    }
    const valid = await verifySignature(
      SENDGRID_INBOUND_VERIFICATION_KEY, sig, ts, bodyText,
    );
    if (!valid) {
      return new Response("Invalid signature", { status: 403 });
    }
  }

  const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

  let formData: FormData;
  try {
    const req2 = new Request(req.url, {
      method: req.method,
      headers: req.headers,
      body: bodyText,
    });
    formData = await req2.formData();
  } catch (err) {
    console.error("Failed to parse form data:", err);
    return new Response("Bad Request", { status: 200 }); // 200 so SendGrid doesn't retry
  }

  const toAddress   = formData.get("to")?.toString() ?? "";
  const fromAddress = formData.get("from")?.toString() ?? "";
  const subject     = formData.get("subject")?.toString() ?? null;
  const bodyTxt     = formData.get("text")?.toString() ?? null;
  const headersStr  = formData.get("headers")?.toString() ?? "";
  const rawPayload: Record<string, string> = {};
  for (const [k, v] of formData.entries()) {
    if (typeof v === "string") rawPayload[k] = v;
  }

  const parsedHeaders = parseHeadersString(headersStr);
  const messageId  = parsedHeaders["message-id"] ?? null;
  const inReplyTo  = parsedHeaders["in-reply-to"] ?? null;

  const reply_domain = `reply.${APP_DOMAIN}`;
  const to_valid = toAddress.endsWith(`@${reply_domain}`);

  const { error } = await supabase.from("dietary_inbound_messages").insert({
    from_address: fromAddress,
    subject,
    body_text: bodyTxt,
    message_id: messageId,
    in_reply_to: inReplyTo,
    to_address: to_valid ? toAddress : null,
    raw_payload: rawPayload,
  });

  if (error) {
    console.error("Supabase insert error:", error);
    // Return 200 so SendGrid does not retry — the error is logged for debugging.
    return new Response("Internal error (logged)", { status: 200 });
  }

  return new Response("OK", { status: 200 });
});
