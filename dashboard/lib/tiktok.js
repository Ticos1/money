// Conexão com o TikTok (Login Kit). O token de renovação é guardado no repositório
// CRIPTOGRAFADO (AES-GCM), com chave derivada de MEDIA_SIGNING_SECRET — a mesma
// derivação usada em app/publishers/tiktok.py.
import { safeEqual } from "./auth.js";

const enc = new TextEncoder();
export const SCOPES = "user.info.basic,video.upload";

export function redirectUri(url) {
  return `${new URL(url).origin}/api/tiktok/callback`;
}

async function aesKey(secret) {
  const digest = await crypto.subtle.digest("SHA-256", enc.encode(`${secret}|tiktok`));
  return crypto.subtle.importKey("raw", digest, "AES-GCM", false, ["encrypt"]);
}

export async function encryptToken(text, secret) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await aesKey(secret), enc.encode(text)));
  const all = new Uint8Array(iv.length + ct.length);
  all.set(iv);
  all.set(ct, iv.length);
  let s = "";
  for (const b of all) s += String.fromCharCode(b);
  return btoa(s);
}

// "state" assinado: protege o retorno do TikTok contra pedidos forjados.
async function hmacHex(secret, data) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
  return [...mac].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function makeState(secret) {
  const exp = Date.now() + 10 * 60 * 1000;
  return `${exp}.${await hmacHex(secret, `tiktok-state:${exp}`)}`;
}

export async function checkState(state, secret) {
  const [exp, sig] = String(state || "").split(".");
  if (!exp || Number(exp) < Date.now()) return false;
  return safeEqual(sig || "", await hmacHex(secret, `tiktok-state:${exp}`));
}
