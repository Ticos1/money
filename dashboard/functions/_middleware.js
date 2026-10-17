// Protege TODO o painel (páginas, API e mídias): só entra quem fez login.
import { hasValidMediaSignature, hasValidSession } from "../lib/auth.js";

const PUBLIC = new Set(["/login", "/login.html", "/api/login", "/style.css", "/icon.svg",
  "/api/tiktok/callback", "/sobre", "/sobre.html", "/termos", "/termos.html", "/privacidade", "/privacidade.html"]);

const SECURITY_HEADERS = {
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "same-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  "Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
    + "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
    + "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
};

// páginas geradas por app/site.py; das mídias, só as imagens do Versículo do dia são públicas
const PUBLIC_SITE = /^\/(hoje|dia)(\/|$)|^\/(robots\.txt|sitemap\.xml)$|^\/google[\w-]+\.html$/;
const PUBLIC_VERSE_IMAGE = /^\/media\/\d{4}-\d{2}-\d{2}\/\d{4}-\d{2}-\d{2}-\d+-verse(-v\d+)?\/imagem_[a-z]+\.jpg$/;

function isPublicSite(pathname) {
  return PUBLIC_SITE.test(pathname) || PUBLIC_VERSE_IMAGE.test(pathname);
}

function withHeaders(res) {
  const out = new Response(res.body, res);
  for (const [k, v] of Object.entries(SECURITY_HEADERS)) out.headers.set(k, v);
  return out;
}

export async function onRequest(ctx) {
  const { request, env } = ctx;
  const url = new URL(request.url);

  if (!env.DASHBOARD_PASSWORD || !env.SESSION_SECRET || env.SESSION_SECRET.length < 32) {
    return new Response(
      "Painel ainda não configurado: defina DASHBOARD_PASSWORD e SESSION_SECRET (32+ caracteres) no Cloudflare Pages.",
      { status: 500, headers: { "Content-Type": "text/plain; charset=utf-8" } },
    );
  }

  // Bloqueia requisições de outros sites (CSRF) em operações que alteram dados.
  if (!["GET", "HEAD"].includes(request.method)) {
    const origin = request.headers.get("Origin");
    if (origin && origin !== url.origin) return new Response("Origem inválida", { status: 403 });
  }

  // arquivos de verificação de domínio do TikTok (ex.: /tiktokAbC123.txt) também são públicos
  if (PUBLIC.has(url.pathname) || /^\/tiktok[\w-]+\.txt$/.test(url.pathname)) return withHeaders(await ctx.next());

  // mini-site público (versículo do dia + quiz de hoje) e a imagem do versículo usada na prévia do link
  if (["GET", "HEAD"].includes(request.method) && isPublicSite(url.pathname)) return withHeaders(await ctx.next());

  // Instagram/Facebook baixam a mídia por um link assinado que expira em poucas horas.
  if (["GET", "HEAD"].includes(request.method) && (await hasValidMediaSignature(url, env.MEDIA_SIGNING_SECRET))) {
    return withHeaders(await ctx.next());
  }

  if (await hasValidSession(request, env.SESSION_SECRET)) return withHeaders(await ctx.next());

  // visitante sem login no endereço principal (ex.: link da bio) vai para o versículo do dia
  if (url.pathname === "/" && request.method === "GET") return Response.redirect(`${url.origin}/hoje/`, 302);

  if (url.pathname.startsWith("/api/")) {
    return new Response(JSON.stringify({ error: "login necessário" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }
  return Response.redirect(`${url.origin}/login`, 302);
}
