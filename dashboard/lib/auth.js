// Sessão do painel: cookie assinado com HMAC-SHA256 (Web Crypto, sem dependências).
const enc = new TextEncoder();
export const COOKIE = "sessao";

function b64url(buf) {
  let s = "";
  for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function hmac(secret, data) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
}

export function safeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

// Compara as senhas via HMAC para o tempo de resposta não revelar nada.
export async function checkPassword(input, expected, secret) {
  return safeEqual(await hmac(secret, `pw:${input}`), await hmac(secret, `pw:${expected}`));
}

export async function createSessionCookie(secret, days = 30) {
  const exp = Date.now() + days * 86400000;
  const value = `${exp}.${await hmac(secret, `s:${exp}`)}`;
  return `${COOKIE}=${value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${days * 86400}`;
}

export function clearSessionCookie() {
  return `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0`;
}

export async function hasValidSession(request, secret) {
  const cookies = request.headers.get("Cookie") || "";
  const match = cookies.match(new RegExp(`(?:^|;\\s*)${COOKIE}=([^;]+)`));
  if (!match) return false;
  const [exp, sig] = match[1].split(".");
  if (!exp || !sig || Number(exp) < Date.now()) return false;
  return safeEqual(sig, await hmac(secret, `s:${exp}`));
}

// Links temporários de mídia para as redes baixarem (assinados pelo GitHub Actions).
export async function hasValidMediaSignature(url, secret) {
  if (!secret || secret.length < 32 || !url.pathname.startsWith("/media/")) return false;
  const exp = url.searchParams.get("exp");
  const sig = url.searchParams.get("sig") || "";
  if (!exp || Number(exp) * 1000 < Date.now()) return false;
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(`${url.pathname}|${exp}`)));
  const hex = [...mac].map((b) => b.toString(16).padStart(2, "0")).join("");
  return safeEqual(sig, hex);
}

// Limite de tentativas de login por IP (5 erros em 15 min). Usa o cache do Cloudflare,
// que é por região: freia tentativa em massa, mas não é um contador global exato.
const MAX_FAILURES = 5;
const WINDOW_SECONDS = 900;

function limiterKey(request) {
  const ip = request.headers.get("CF-Connecting-IP") || "desconhecido";
  return new Request(`https://limite.interno/login/${encodeURIComponent(ip)}`);
}

export async function loginFailures(request) {
  try {
    const hit = await caches.default.match(limiterKey(request));
    return hit ? Number(await hit.text()) || 0 : 0;
  } catch {
    return 0;
  }
}

export async function isLoginBlocked(request) {
  return (await loginFailures(request)) >= MAX_FAILURES;
}

export async function recordLoginFailure(request) {
  try {
    const n = (await loginFailures(request)) + 1;
    await caches.default.put(limiterKey(request), new Response(String(n), {
      headers: { "Cache-Control": `max-age=${WINDOW_SECONDS}` },
    }));
  } catch {
    // sem cache disponível: segue só com o atraso por tentativa
  }
}

export async function clearLoginFailures(request) {
  try {
    await caches.default.delete(limiterKey(request));
  } catch {
    // nada a limpar
  }
}
