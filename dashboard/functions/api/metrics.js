import { GitHub, json } from "../../lib/github.js";

// GET: métricas coletadas (state/metrics.json). POST: pede uma coleta nova.
export async function onRequestGet({ env }) {
  try {
    const { data } = await new GitHub(env).getJson("state/metrics.json", { posts: {}, notes: [] });
    return json(data);
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}

export async function onRequestPost({ env }) {
  try {
    await new GitHub(env).dispatch({ post_id: "", platform: "", agora: "false" }, "publish.yml");
    return json({ ok: true });
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}
