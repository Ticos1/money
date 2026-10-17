import { GitHub, json } from "../../lib/github.js";

// Configurações → "Gerar só o que falta" (clear: false, padrão) ou "Refazer o dia do zero"
// (clear: true, apaga a fila): dispara o GitHub Actions fora do horário agendado.
export async function onRequestPost({ request, env }) {
  try {
    const body = await request.json().catch(() => ({}));
    if (body.compilation) {
      await new GitHub(env).dispatch({ mode: "compilation", force: "false", clear: "false" });
      return json({ ok: true });
    }
    await new GitHub(env).dispatch({
      mode: "generate",
      force: body.force ? "true" : "false",
      clear: body.clear === true ? "true" : "false",
    });
    return json({ ok: true });
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}
