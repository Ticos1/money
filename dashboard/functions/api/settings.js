import { GitHub, json } from "../../lib/github.js";

const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
const TYPES = ["verse", "quiz", "curiosity", "fill", "truefalse"];
const MODEL = /^[\w./:-]{3,80}$/;

// Salva as configurações editáveis pelo painel em config/settings.json.
export async function onRequestPut({ request, env }) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "requisição inválida" }, 400);
  }
  const slots = Array.isArray(body.slots) ? body.slots : [];
  if (slots.length < 1 || slots.length > 12) return json({ error: "Use de 1 a 12 horários" }, 400);
  for (const s of slots) {
    if (!TIME.test(s.time || "") || !TYPES.includes(s.type)) return json({ error: "Horário ou tipo inválido" }, 400);
  }
  const comp = body.compilation;
  if (comp && (!TIME.test(comp.time || "") || !(comp.weekday >= 0 && comp.weekday <= 6)
      || !(comp.minutes >= 3 && comp.minutes <= 20))) return json({ error: "Vídeo longo: dia, horário ou minutos inválidos" }, 400);
  const handle = String(body.handle || "").trim().slice(0, 40);
  if (handle && !/^@?[\w.]+$/.test(handle)) return json({ error: "@ inválido" }, 400);
  if (body.model && !MODEL.test(body.model)) return json({ error: "Modelo inválido" }, 400);

  try {
    const gh = new GitHub(env);
    const saved = await gh.update(
      "config/settings.json",
      {},
      (s) => {
        s.brand = { ...(s.brand || {}), name: String(body.name || s.brand?.name || "").slice(0, 40) };
        s.brand.handle = handle ? (handle.startsWith("@") ? handle : `@${handle}`) : "";
        s.schedule = { slots: slots.map((x) => ({ time: x.time, type: x.type })) };
        s.approval = { ...(s.approval || {}), auto_approve: Boolean(body.auto_approve) };
        if (body.publishing && typeof body.publishing === "object") {
          s.publishing = { ...(s.publishing || {}) };
          for (const k of ["instagram", "facebook", "youtube", "stories", "tiktok"]) s.publishing[k] = Boolean(body.publishing[k]);
        }
        if (Array.isArray(body.video_types)) {
          const wanted = new Set(body.video_types);
          s.video = { ...(s.video || {}), video_types: ["quiz", "verse", "curiosity"].filter((t) => t === "quiz" || wanted.has(t)) };
        }
        if (comp) {
          s.compilation = { enabled: Boolean(comp.enabled), weekday: Math.round(comp.weekday),
            time: comp.time, minutes: Math.round(comp.minutes) };
        }
        s.groq = { ...(s.groq || {}) };
        s.groq.enabled = Boolean(body.groq_enabled);
        if (body.model) s.groq.model = body.model;
        const calls = Number(body.max_calls_per_day);
        if (calls >= 0 && calls <= 50) s.groq.max_calls_per_day = Math.round(calls);
        const ratio = Number(body.new_content_ratio);
        if (ratio >= 0 && ratio <= 1) s.groq.new_content_ratio = ratio;
        return s;
      },
      "painel: configurações",
    );
    return json({ ok: true, settings: saved });
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}
