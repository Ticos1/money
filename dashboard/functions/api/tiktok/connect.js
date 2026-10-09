import { makeState, redirectUri, SCOPES } from "../../../lib/tiktok.js";

// Botão "Conectar TikTok": leva para a tela de autorização do TikTok.
export async function onRequestGet({ request, env }) {
  if (!env.TIKTOK_CLIENT_KEY || !env.TIKTOK_CLIENT_SECRET) {
    return new Response("Configure TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET no Cloudflare (veja docs/TIKTOK.md).",
      { status: 500, headers: { "Content-Type": "text/plain; charset=utf-8" } });
  }
  const url = new URL("https://www.tiktok.com/v2/auth/authorize/");
  url.searchParams.set("client_key", env.TIKTOK_CLIENT_KEY);
  url.searchParams.set("scope", SCOPES);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("redirect_uri", redirectUri(request.url));
  url.searchParams.set("state", await makeState(env.SESSION_SECRET));
  return Response.redirect(url.toString(), 302);
}
