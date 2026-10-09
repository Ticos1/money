import { GitHub, json } from "../../lib/github.js";

// Fila de posts + configurações, lidas direto do repositório.
export async function onRequestGet({ env }) {
  try {
    const gh = new GitHub(env);
    const [queue, settings, groq] = await Promise.all([
      gh.getJson("state/queue.json", { posts: [] }),
      gh.getJson("config/settings.json", {}),
      gh.getJson("state/groq.json", { date: "", calls: 0 }),
    ]);
    return json({ posts: queue.data.posts, settings: settings.data, groq: groq.data });
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}
