import {
  checkPassword, clearLoginFailures, createSessionCookie, isLoginBlocked, recordLoginFailure,
} from "../../lib/auth.js";
import { json } from "../../lib/github.js";

export async function onRequestPost({ request, env }) {
  if (await isLoginBlocked(request)) {
    return json({ error: "Muitas tentativas. Aguarde 15 minutos." }, 429);
  }
  let password = "";
  try {
    password = String((await request.json()).password || "");
  } catch {
    return json({ error: "requisição inválida" }, 400);
  }
  if (!(await checkPassword(password, env.DASHBOARD_PASSWORD, env.SESSION_SECRET))) {
    await recordLoginFailure(request);
    await new Promise((r) => setTimeout(r, 1500)); // atrasa tentativas de adivinhar a senha
    return json({ error: "Senha incorreta" }, 401);
  }
  await clearLoginFailures(request);
  const res = json({ ok: true });
  res.headers.append("Set-Cookie", await createSessionCookie(env.SESSION_SECRET));
  return res;
}
