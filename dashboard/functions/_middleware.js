// Protege TODO o painel (páginas, API e mídias): só entra quem fez login.
import { hasValidSession } from "../lib/auth.js";

const PUBLIC = new Set(["/login", "/login.html", "/api/login", "/style.css", "/icon.svg"]);

const SECURITY_HEADERS = {
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "same-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
};

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

  if (PUBLIC.has(url.pathname)) return withHeaders(await ctx.next());

  if (await hasValidSession(request, env.SESSION_SECRET)) return withHeaders(await ctx.next());

  if (url.pathname.startsWith("/api/")) {
    return new Response(JSON.stringify({ error: "login necessário" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }
  return Response.redirect(`${url.origin}/login`, 302);
}
