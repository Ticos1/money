// Agendador: o cron do GitHub Actions atrasa/pula execuções em horários cheios,
// então quem decide QUANDO rodar é este Worker (Cloudflare Cron, a cada 5 min).
// Precisa das variáveis GITHUB_TOKEN e GITHUB_REPO (as mesmas do painel).
import { GitHub } from "../dashboard/lib/github.js";
import { NETS, applies, dueAt, nowIn } from "../dashboard/lib/rules.js";

const GENERATE_AFTER = "05:20"; // horário de Brasília: se ainda não gerou o dia, gera

// Post aprovado, no horário, com alguma rede ligada ainda sem publicar (e sem erro esgotado).
// Com publishing.paused (botão "Pausar publicações" do painel) nada é publicado.
export function needsPublishing(post, settings, now) {
  if (settings.publishing?.paused) return false;
  if (post.status !== "approved" || !post.media?.base) return false;
  if (dueAt(post) > `${now.date} ${now.time}`) return false;
  const pub = settings.publishing || {};
  const max = Number(pub.max_attempts || 3);
  return NETS.some((n) => pub[n] && applies(n, post, pub) && !post.published?.[n] && !post.publish_skipped?.[n]
    && ((post.publish_errors?.[n]?.attempts) || 0) < max);
}

async function busy(gh, workflow) {
  const res = await gh.call(`/repos/${gh.repo}/actions/workflows/${workflow}/runs?per_page=5`);
  if (!res.ok) return true; // na dúvida, não dispara
  const runs = (await res.json()).workflow_runs || [];
  return runs.some((r) => ["queued", "in_progress", "waiting", "requested", "pending"].includes(r.status));
}

export async function tick(env) {
  const gh = new GitHub(env);
  const [{ data: queue }, { data: settings }] = await Promise.all([
    gh.getJson("state/queue.json", { posts: [] }),
    gh.getJson("config/settings.json", {}),
  ]);
  const now = nowIn(settings.timezone || "America/Sao_Paulo");
  const log = [];

  // 1) geração diária (o pipeline.yml não tem mais cron próprio: só este Worker dispara)
  if (now.time >= GENERATE_AFTER) {
    let generated = queue.posts.some((p) => p.date === now.date);
    if (!generated) {
      const { data: history } = await gh.getJson("state/history.json", { posts: [] });
      generated = history.posts.some((p) => p.date === now.date);
    }
    if (!generated && !(await busy(gh, "pipeline.yml"))) {
      await gh.dispatch({ mode: "generate", force: "false", clear: "false" }, "pipeline.yml");
      log.push(`gerar ${now.date}`);
    }
  }

  // 2) publicação dos posts no horário (a mesma rodada também atualiza as métricas)
  const due = queue.posts.filter((p) => needsPublishing(p, settings, now));
  let metricsStale = false;
  if (!due.length && now.time >= "06:00") {
    const { data: metrics } = await gh.getJson("state/metrics.json", {});
    metricsStale = !metrics.updated_at || Date.now() - Date.parse(metrics.updated_at) > 3 * 3600e3;
  }
  if ((due.length || metricsStale) && !(await busy(gh, "publish.yml"))) {
    await gh.dispatch({ post_id: "", platform: "", agora: "false" }, "publish.yml");
    log.push(due.length ? `publicar ${due.map((p) => p.id).join(", ")}` : "atualizar métricas");
  }
  return log;
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(tick(env).then((log) => log.length && console.log(log.join(" | "))));
  },
};
