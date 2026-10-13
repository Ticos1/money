import { GitHub } from "../../../lib/github.js";
import { checkState, encryptToken, redirectUri } from "../../../lib/tiktok.js";

const esc = (t) => String(t ?? "").replace(/[<>&"']/g, (c) => `&#${c.charCodeAt(0)};`);

// `msg` pode conter HTML nosso (ex.: <b>); texto vindo de fora passa por esc() antes.
function page(title, msg, ok) {
  return new Response(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/style.css"><div class="login"><div class="card"><h1>${ok ? "✅" : "⚠️"} ${title}</h1>
<p>${msg}</p><p><a class="btn primary" href="/">Voltar ao painel</a></p></div></div>`,
    { status: ok ? 200 : 400, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

// Retorno da autorização do TikTok (rota pública, protegida pelo "state" assinado).
export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  if (url.searchParams.get("error")) {
    return page("Conexão cancelada", "O TikTok não autorizou a conexão. Tente de novo pelo painel.", false);
  }
  if (!(await checkState(url.searchParams.get("state"), env.SESSION_SECRET))) {
    return page("Link expirado", "Volte ao painel e toque em “Conectar TikTok” de novo.", false);
  }
  if (!env.MEDIA_SIGNING_SECRET || env.MEDIA_SIGNING_SECRET.length < 32) {
    return page("Falta configuração", "Configure MEDIA_SIGNING_SECRET no Cloudflare.", false);
  }
  const res = await fetch("https://open.tiktokapis.com/v2/oauth/token/", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_key: env.TIKTOK_CLIENT_KEY,
      client_secret: env.TIKTOK_CLIENT_SECRET,
      code: url.searchParams.get("code") || "",
      grant_type: "authorization_code",
      redirect_uri: redirectUri(request.url),
    }),
  });
  const tok = await res.json().catch(() => ({}));
  if (!tok.refresh_token) {
    return page("Erro do TikTok", `O TikTok recusou: ${esc(tok.error_description || tok.error || res.status)}`, false);
  }
  if (!String(tok.scope || "").includes("video.upload")) {
    return page("Permissão faltando", "Autorize o envio de vídeos (video.upload) ao conectar.", false);
  }
  let name = "";
  try {
    const info = await fetch("https://open.tiktokapis.com/v2/user/info/?fields=display_name", {
      headers: { Authorization: `Bearer ${tok.access_token}` },
    }).then((r) => r.json());
    name = info?.data?.user?.display_name || "";
  } catch {
    // o nome é só informativo
  }
  const record = {
    open_id: tok.open_id,
    display_name: name,
    scope: tok.scope,
    connected_at: new Date().toISOString(),
    refresh_expires_at: Math.floor(Date.now() / 1000) + Number(tok.refresh_expires_in || 0),
    refresh_token_enc: await encryptToken(tok.refresh_token, env.MEDIA_SIGNING_SECRET),
  };
  try {
    await new GitHub(env).update("state/tiktok.json", {}, (d) => {
      for (const k of Object.keys(d)) delete d[k];
      Object.assign(d, record);
    }, "painel: conectar TikTok");
  } catch (err) {
    return page("Erro ao salvar", esc(err.message), false);
  }
  return page("TikTok conectado!", `Conta conectada${name ? `: <b>${esc(name)}</b>` : ""}. Agora ligue o TikTok em Configurações.`, true);
}
