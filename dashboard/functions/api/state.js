import { GitHub, json } from "../../lib/github.js";

// Fila de posts + configurações + resumo de saúde (aba Hoje), numa chamada só ao GitHub.
export async function onRequestGet({ env }) {
  try {
    const gh = new GitHub(env);
    const f = await gh.getMany({
      queue: ["state/queue.json", { posts: [] }],
      settings: ["config/settings.json", {}],
      groq: ["state/groq.json", { date: "", calls: 0 }],
      tiktok: ["state/tiktok.json", {}],
      health: ["state/health.json", null],
    });
    const t = f.tiktok.data || {};
    const tiktokStatus = t.refresh_token_enc
      ? { connected: true, name: t.display_name || "", expires_at: t.refresh_expires_at || 0 }
      : { connected: false };
    return json({ posts: f.queue.data.posts, settings: f.settings.data, groq: f.groq.data, tiktok: tiktokStatus,
      health: f.health.data });
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}
