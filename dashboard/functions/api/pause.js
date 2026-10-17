import { GitHub, json } from "../../lib/github.js";
import { dueAt, missingNets, nowIn } from "../../lib/rules.js";

const PAUSE_SKIP = "pulado: publicações pausadas";

// Botão "Pausar publicações" (dias de luto, tragédia ou viagem): grava publishing.paused.
// Ao retomar com skip_missed, os posts cujo horário passou durante a pausa não saem mais
// (ficam como "pulados" e vão para o Histórico), para não sair tudo de uma vez.
export async function onRequestPost({ request, env }) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "requisição inválida" }, 400);
  }
  const paused = Boolean(body.paused);
  try {
    const gh = new GitHub(env);
    const settings = await gh.update("config/settings.json", {}, (s) => {
      s.publishing = { ...(s.publishing || {}), paused };
      if (paused) {
        s.publishing.paused_at = new Date().toISOString();
        s.publishing.paused_reason = String(body.reason || "").trim().slice(0, 120);
      } else {
        delete s.publishing.paused_at;
        delete s.publishing.paused_reason;
      }
      return s;
    }, paused ? "painel: pausar publicações" : "painel: retomar publicações");
    let skipped = 0;
    if (!paused && body.skip_missed) {
      const now = nowIn(settings.timezone || "America/Sao_Paulo");
      skipped = await gh.update("state/queue.json", { posts: [] }, (q) => {
        let n = 0;
        for (const p of q.posts) {
          if (p.status !== "approved" || !p.media?.base || dueAt(p) > `${now.date} ${now.time}`) continue;
          const nets = missingNets(p, settings.publishing);
          if (!nets.length) continue;
          p.publish_skipped = p.publish_skipped || {};
          for (const k of nets) p.publish_skipped[k] = PAUSE_SKIP;
          n += 1;
        }
        return n;
      }, "painel: pula os posts atrasados da pausa");
    }
    return json({ ok: true, settings, skipped });
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}
