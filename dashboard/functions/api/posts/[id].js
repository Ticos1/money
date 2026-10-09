import { GitHub, json } from "../../../lib/github.js";

const PLATFORMS = ["tiktok", "kwai", "youtube", "instagram", "facebook"];
const VISUAL_FIELDS = {
  verse: ["on_screen", "reflection"],
  quiz: ["question", "options", "answer"],
};

function clean(text, max) {
  return String(text ?? "").replace(/\r/g, "").slice(0, max);
}

// Ações do painel sobre um post: aprovar, rejeitar, editar, marcar como publicado.
export async function onRequestPost({ request, env, params }) {
  const id = params.id;
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "requisição inválida" }, 400);
  }
  try {
    const gh = new GitHub(env);
    let rerender = false;
    const post = await gh.update(
      "state/queue.json",
      { posts: [] },
      (queue) => {
        const p = queue.posts.find((x) => x.id === id);
        if (!p) throw new Error("post não encontrado");
        switch (body.action) {
          case "approve":
            p.status = "approved";
            break;
          case "reject":
            p.status = "rejected";
            break;
          case "pending":
            p.status = "pending";
            break;
          case "published": {
            if (!PLATFORMS.includes(body.platform)) throw new Error("plataforma inválida");
            p.published = p.published || {};
            p.published[body.platform] = body.value ? new Date().toISOString() : null;
            break;
          }
          case "edit": {
            const caps = body.captions || {};
            for (const k of ["instagram", "facebook", "tiktok", "kwai"]) {
              if (k in caps) p.captions[k] = clean(caps[k], 2200);
            }
            if (caps.youtube) {
              p.captions.youtube.title = clean(caps.youtube.title, 100);
              p.captions.youtube.description = clean(caps.youtube.description, 4900);
            }
            const changes = body.content || {};
            for (const field of VISUAL_FIELDS[p.type] || []) {
              if (!(field in changes)) continue;
              let value = changes[field];
              if (field === "options") value = (Array.isArray(value) ? value : []).slice(0, 4).map((o) => clean(o, 60));
              else if (field === "answer") value = Math.max(0, Math.min(3, Number(value) || 0));
              else value = clean(value, field === "reflection" ? 600 : 160);
              if (JSON.stringify(p.content[field]) !== JSON.stringify(value)) {
                p.content[field] = value;
                rerender = true;
              }
            }
            if (rerender) {
              p.needs_render = true;
              p.error = null;
            }
            break;
          }
          default:
            throw new Error("ação desconhecida");
        }
        return p;
      },
      `painel: ${body.action} ${id}`,
    );
    if (rerender) await gh.dispatch({ mode: "rerender", post_id: id, force: "false" });
    // Aprovou: tenta publicar já (se o horário do post já chegou e houver rede ligada).
    let publishing = false;
    if (body.action === "approve" && !rerender) {
      try {
        await gh.dispatch({ post_id: id }, "publish.yml");
        publishing = true;
      } catch {
        // sem permissão ou workflow ausente: a rodada de hora em hora publica depois
      }
    }
    return json({ ok: true, post, rerender, publishing });
  } catch (err) {
    return json({ error: err.message }, 400);
  }
}
