import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const SENDGRID_INBOUND_VERIFICATION_KEY = Deno.env.get("SENDGRID_INBOUND_VERIFICATION_KEY") ?? "";

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

// Parse headers and text/plain body from the raw MIME email string SendGrid
// provides in the `email` form field. Handles CRLF line endings and RFC 2822
// header folding (continuation lines starting with whitespace).
function parseRawEmail(rawEmail: string): {
  headers: Record<string, string>;
  bodyText: string | null;
} {
  const splitAt = rawEmail.indexOf("\r\n\r\n");
  if (splitAt === -1) return { headers: {}, bodyText: null };

  const headerSection = rawEmail.slice(0, splitAt);
  const bodySection = rawEmail.slice(splitAt + 4);

  // Unfold folded headers before splitting into lines
  const unfolded = headerSection.replace(/\r\n[ \t]+/g, " ");
  const headers: Record<string, string> = {};
  for (const line of unfolded.split("\r\n")) {
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim().toLowerCase();
    const val = line.slice(idx + 1).trim();
    if (key && !(key in headers)) headers[key] = val; // first occurrence wins
  }

  // Extract the text/plain part from the body
  const contentType = headers["content-type"] ?? "";
  let bodyText: string | null = null;

  if (contentType.includes("multipart/")) {
    const m = contentType.match(/boundary="([^"]+)"/);
    if (m) {
      const boundary = "--" + m[1];
      for (const part of bodySection.split(boundary)) {
        const partSplit = part.indexOf("\r\n\r\n");
        if (partSplit === -1) continue;
        const partHead = part.slice(0, partSplit);
        const partBody = part.slice(partSplit + 4);
        if (partHead.toLowerCase().includes("text/plain")) {
          const enc = (partHead.match(/content-transfer-encoding:\s*(\S+)/i) ?? [])[1] ?? "";
          // Decode quoted-printable soft line breaks; leave other encoded chars as-is
          bodyText = enc.toLowerCase() === "quoted-printable"
            ? partBody.replace(/=\r\n/g, "").trim()
            : partBody.trim();
          break;
        }
      }
    }
  } else if (contentType.includes("text/plain")) {
    const enc = headers["content-transfer-encoding"] ?? "";
    bodyText = enc.toLowerCase() === "quoted-printable"
      ? bodySection.replace(/=\r\n/g, "").trim()
      : bodySection.trim();
  }

  return { headers, bodyText };
}

// Strip display name from RFC 2822 address — "Alice <alice@example.com>" → "alice@example.com"
function extractEmail(addr: string): string {
  const m = addr.match(/<([^>]+)>/);
  return m ? m[1].trim() : addr.trim();
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

  // Use the SMTP envelope for a clean recipient address — the To: header can
  // be malformed (e.g. Outlook sends `"addr"\t<addr>`), but the envelope is
  // always the raw RCPT TO value.
  const envelopeStr = formData.get("envelope")?.toString() ?? "{}";
  let toAddress = "";
  try {
    const env = JSON.parse(envelopeStr);
    toAddress = (env.to as string[])?.[0] ?? "";
  } catch { /* fall through to empty string */ }

  const fromAddress = extractEmail(formData.get("from")?.toString() ?? "");
  const subject     = formData.get("subject")?.toString() ?? null;

  // SendGrid posts the full raw MIME in the `email` field; parse it for
  // headers (message-id, in-reply-to) and the plain-text body.
  const rawEmail = formData.get("email")?.toString() ?? "";
  const { headers, bodyText: parsedBody } = parseRawEmail(rawEmail);
  const messageId = headers["message-id"] ?? null;
  const inReplyTo = headers["in-reply-to"] ?? null;

  const rawPayload: Record<string, string> = {};
  for (const [k, v] of formData.entries()) {
    if (typeof v === "string") rawPayload[k] = v;
  }

  // Route to support_inbound_messages if the recipient local part is "support"
  // (i.e. support@reply.<domain>); dietary replies use replies+CODE@reply.<domain>
  const localPart = toAddress.split("@")[0] ?? "";
  const table = localPart === "support" ? "support_inbound_messages" : "dietary_inbound_messages";

  const { error } = await supabase.from(table).insert({
    from_address: fromAddress,
    subject,
    body_text: parsedBody,
    message_id: messageId,
    in_reply_to: inReplyTo,
    to_address: toAddress || null,
    raw_payload: rawPayload,
  });

  if (error) {
    console.error("Supabase insert error:", error);
    // Return 200 so SendGrid does not retry — the error is logged for debugging.
    return new Response("Internal error (logged)", { status: 200 });
  }

  return new Response("OK", { status: 200 });
});
