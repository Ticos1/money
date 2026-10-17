import { GitHub, json } from "../../lib/github.js";
import { postTitle } from "../../lib/rules.js";

const CACHE_KEY = "https://painel.cache/state/history.json";
const CACHE_SECONDS = 120; // o histórico só muda quando um post sai da fila
const SLIM = ["id", "date", "time", "type", "status", "published", "publish_links", "publish_errors",
  "publish_skipped", "repost_of"];

// Histórico em páginas: o state/history.json inteiro fica no servidor (com cache curto)
// e o painel recebe só o mês pedido, já filtrado e sem legendas.
//   ?month=AAAA-MM (padrão: o mais recente) · ?type=quiz · ?net=facebook · ?errors=1
//   ?id=<post> devolve o post completo (para abrir o card)
async function loadHistory(env) {
  const cache = typeof caches !== "undefined" ? caches.default : null;
  const hit = cache && (await cache.match(CACHE_KEY));
  if (hit) return hit.json();
  const { data } = await new GitHub(env).getJson("state/history.json", { posts: [] });
  if (cache) {
    await cache.put(CACHE_KEY, new Response(JSON.stringify(data), {
      headers: { "Content-Type": "application/json", "Cache-Control": `max-age=${CACHE_SECONDS}` },
    }));
  }
  return data;
}

export async function onRequestGet({ request, env }) {
  try {
    const q = new URL(request.url).searchParams;
    const posts = (await loadHistory(env)).posts || [];
    if (q.get("id")) {
      const post = posts.find((p) => p.id === q.get("id"));
      return post ? json({ post }) : json({ error: "post não encontrado no histórico" }, 404);
    }
    const months = {};
    for (const p of posts) {
      const m = (p.date || "").slice(0, 7);
      if (m) months[m] = (months[m] || 0) + 1;
    }
    const list = Object.keys(months).sort().reverse();
    const month = q.get("month") || list[0] || "";
    const type = q.get("type"), net = q.get("net"), errors = q.get("errors") === "1";
    const out = posts.filter((p) => (p.date || "").startsWith(month)
      && (!type || p.type === type)
      && (!net || p.published?.[net] || p.publish_errors?.[net] || p.publish_skipped?.[net])
      && (!errors || Object.keys(p.publish_errors || {}).length > 0))
      .map((p) => ({ ...Object.fromEntries(SLIM.filter((k) => k in p).map((k) => [k, p[k]])), title: postTitle(p) }));
    return json({ month, months: list.map((m) => ({ month: m, posts: months[m] })), posts: out });
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}
