import { checkPassword, createSessionCookie } from "../../lib/auth.js";
import { json } from "../../lib/github.js";

export async function onRequestPost({ request, env }) {
  let password = "";
  try {
    password = String((await request.json()).password || "");
  } catch {
    return json({ error: "requisição inválida" }, 400);
  }
  if (!(await checkPassword(password, env.DASHBOARD_PASSWORD, env.SESSION_SECRET))) {
    await new Promise((r) => setTimeout(r, 1500)); // atrasa tentativas de adivinhar a senha
    return json({ error: "Senha incorreta" }, 401);
  }
  const res = json({ ok: true });
  res.headers.append("Set-Cookie", await createSessionCookie(env.SESSION_SECRET));
  return res;
}
