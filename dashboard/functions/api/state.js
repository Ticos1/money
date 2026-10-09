import { GitHub, json } from "../../lib/github.js";

// Fila de posts + configurações, lidas direto do repositório.
export async function onRequestGet({ env }) {
  try {
    const gh = new GitHub(env);
    const [queue, settings, groq, tiktok] = await Promise.all([
      gh.getJson("state/queue.json", { posts: [] }),
      gh.getJson("config/settings.json", {}),
      gh.getJson("state/groq.json", { date: "", calls: 0 }),
      gh.getJson("state/tiktok.json", {}),
    ]);
    const t = tiktok.data || {};
    const tiktokStatus = t.refresh_token_enc
      ? { connected: true, name: t.display_name || "", expires_at: t.refresh_expires_at || 0 }
      : { connected: false };
    return json({ posts: queue.data.posts, settings: settings.data, groq: groq.data, tiktok: tiktokStatus });
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}
