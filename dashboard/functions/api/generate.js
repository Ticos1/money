import { GitHub, json } from "../../lib/github.js";

// Botão "Gerar agora": dispara o GitHub Actions fora do horário agendado.
export async function onRequestPost({ request, env }) {
  try {
    const body = await request.json().catch(() => ({}));
    await new GitHub(env).dispatch({ mode: "generate", force: body.force ? "true" : "false" });
    return json({ ok: true });
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}
