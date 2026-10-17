// Regras compartilhadas pelo painel (functions/) e pelo agendador (scheduler/worker.js).
// Espelham app/publish.py: mude lá e aqui juntos.

export const NETS = ["instagram", "facebook", "youtube", "stories", "tiktok"];

export function nowIn(tz) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date()).map((p) => [p.type, p.value]));
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
}

export function applies(net, post, pub = {}) {
  const only = pub[`${net}_types`]; // ex.: youtube_types, facebook_types
  if (Array.isArray(only) && !only.includes(post.type)) return false;
  if (post.type === "compilation") return net === "youtube" && Boolean(post.media?.video_music);
  const times = pub[`${net}_times`]; // ex.: instagram_times: só nesses horários da grade
  if (Array.isArray(times) && !times.includes(post.time)) return false;
  if (net === "youtube") return Boolean(post.media?.video_music);
  if (net === "tiktok") return Boolean(post.media?.video_silent);
  if (net === "stories") return Boolean(post.media?.video_music || post.media?.images?.includes("imagem_story.jpg"));
  return true;
}

// Horário real do post: publish_at (slot ± alguns minutos, sorteado na geração) ou o do slot.
export const dueAt = (post) => (post.publish_at || `${post.date}T${post.time}`).replace("T", " ");

// Redes ligadas em que o post ainda não saiu (nem foi pulado).
export function missingNets(post, pub = {}) {
  return NETS.filter((n) => pub[n] && applies(n, post, pub) && !post.published?.[n] && !post.publish_skipped?.[n]);
}

export function postTitle(post) {
  const c = post.content || {};
  if (post.type === "fill") return `Complete: ${c.ref_label}`;
  if (post.type === "book") return `Em qual livro? ${c.ref_label}`;
  if (post.type === "truefalse") return `${c.question} → ${c.shown}?`;
  if (post.type === "verse") return c.ref_label;
  return c.title || c.question || post.id;
}
