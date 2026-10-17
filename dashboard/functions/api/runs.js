import { GitHub, json } from "../../lib/github.js";

const ACTIVE = ["queued", "in_progress", "waiting", "requested", "pending"];

// Execuções do GitHub Actions em andamento (o painel mostra "Gerando…" e atualiza sozinho).
export async function onRequestGet({ env }) {
  try {
    const gh = new GitHub(env);
    const res = await gh.call(`/repos/${gh.repo}/actions/runs?per_page=15`);
    if (!res.ok) return json({ error: `GitHub ${res.status} ao ler as execuções` }, 502);
    const runs = (await res.json()).workflow_runs || [];
    const pick = (file) => {
      const r = runs.find((x) => x.path?.endsWith(`/${file}`) && ACTIVE.includes(x.status));
      return r ? { status: r.status, event: r.event, started_at: r.run_started_at || r.created_at, url: r.html_url } : null;
    };
    return json({ pipeline: pick("pipeline.yml"), publish: pick("publish.yml") });
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}
