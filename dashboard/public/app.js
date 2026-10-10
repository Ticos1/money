"use strict";
// Painel: fila de posts, pré-visualização, download, legendas e histórico.

const PLATFORMS = [
  ["instagram", "Instagram"], ["facebook", "Facebook"], ["tiktok", "TikTok"],
  ["kwai", "Kwai"], ["youtube", "YouTube"],
];
const TYPE_NAME = { verse: "Versículo do dia", quiz: "Desafio de quiz (Reels)", curiosity: "Você sabia?" };
const STATUS_NAME = { pending: "Aguardando aprovação", approved: "Aprovado", rejected: "Rejeitado" };
const IMG_NAME = {
  "imagem_quadrada.jpg": "Imagem 1:1", "imagem_vertical.jpg": "Imagem 4:5", "imagem_story.jpg": "Imagem 9:16",
  "pergunta_quadrada.jpg": "Pergunta 1:1", "pergunta_vertical.jpg": "Pergunta 4:5",
  "resposta_quadrada.jpg": "Resposta 1:1", "resposta_vertical.jpg": "Resposta 4:5",
};

let STATE = { posts: [], settings: {} };
let TAB = "fila";

// ---------- utilidades
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : String(kid));
  return el;
}

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 3200);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401) { location.href = "/login"; throw new Error("login"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Erro ${res.status}`);
  return data;
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copiado!");
  } catch {
    const ta = h("textarea", {}, text);
    document.body.append(ta); ta.select(); document.execCommand("copy"); ta.remove();
    toast("Copiado!");
  }
}

function mediaUrl(post, file) {
  return `/${post.media.base}${file}?v=${post.media.version || 1}`;
}

function fmtDate(post) {
  const d = new Date(`${post.date}T12:00:00`);
  const day = d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
  return `${day} · ${post.time}`;
}

function titleOf(post) {
  if (post.type === "verse") return post.content.ref_label;
  if (post.type === "curiosity") return post.content.title;
  return post.content.question;
}

// ---------- fila
function captionBox(post) {
  const box = h("div");
  const tabs = h("div", { class: "tabs" });
  const body = h("div");
  const show = (key) => {
    [...tabs.children].forEach((b) => b.classList.toggle("on", b.dataset.k === key));
    body.replaceChildren();
    if (key === "youtube") {
      const yt = post.captions.youtube;
      body.append(
        h("div", { class: "muted" }, "Título"), h("pre", { class: "caption" }, yt.title),
        h("button", { class: "btn small", onclick: () => copy(yt.title) }, "Copiar título"), " ",
        h("div", { class: "muted", style: "margin-top:10px" }, "Descrição"), h("pre", { class: "caption" }, yt.description),
        h("button", { class: "btn small", onclick: () => copy(yt.description) }, "Copiar descrição"),
      );
    } else {
      const text = post.captions[key];
      body.append(h("pre", { class: "caption" }, text),
        h("button", { class: "btn small primary", onclick: () => copy(text) }, "Copiar legenda"));
    }
  };
  for (const [k, name] of PLATFORMS) {
    if (k === "youtube" && !post.media?.video_music) continue; // Shorts precisa de vídeo
    tabs.append(h("button", { "data-k": k, onclick: () => show(k) }, name));
  }
  box.append(tabs, body);
  show("instagram");
  return box;
}

function mediaSection(post) {
  if (!post.media || !post.media.base) return h("p", { class: "muted" }, "Sem mídia (post antigo).");
  const m = post.media;
  if (!m.video_music) return imageSection(post);
  const video = h("video", {
    class: "preview", controls: true, playsinline: true, preload: "none",
    poster: mediaUrl(post, m.poster), src: mediaUrl(post, m.video_music),
  });
  const which = h("div", { class: "row", style: "margin-top:8px" },
    h("button", { class: "btn small", onclick: () => { video.src = mediaUrl(post, m.video_music); video.play(); } }, "▶ com música"),
    h("button", { class: "btn small", onclick: () => { video.src = mediaUrl(post, m.video_silent); video.play(); } }, "▶ sem música"),
  );
  const dl = (file, label) => h("a", { class: "btn small", href: mediaUrl(post, file), download: `${post.id}-${file}` }, `⬇ ${label}`);
  const thumbs = h("div", { class: "thumbs" },
    m.images.map((f) => h("a", { href: mediaUrl(post, f), target: "_blank", rel: "noopener", title: IMG_NAME[f] || f },
      h("img", { src: mediaUrl(post, f), alt: IMG_NAME[f] || f, loading: "lazy" }))));
  return h("div", { class: "media" },
    h("div", {}, video, which),
    h("div", {},
      h("h3", {}, "Baixar"),
      h("div", { class: "row" }, dl(m.video_music, "Vídeo com música"), dl(m.video_silent, "Vídeo sem música")),
      h("p", { class: "muted" }, "Com música → YouTube, Facebook (e Instagram, se quiser). Sem música → TikTok, Kwai e Instagram, escolhendo a música no próprio app."),
      thumbs,
      h("div", { class: "row" }, m.images.map((f) => dl(f, IMG_NAME[f] || f))),
      h("p", { class: "muted" }, `Duração: ${m.duration}s`),
    ));
}

// Post só de imagem (ex.: Versículo do dia)
function imageSection(post) {
  const m = post.media;
  const dl = (file) => h("a", { class: "btn small", href: mediaUrl(post, file), download: `${post.id}-${file}` }, `⬇ ${IMG_NAME[file] || file}`);
  return h("div", { class: "media" },
    h("div", {}, h("a", { href: mediaUrl(post, m.poster), target: "_blank", rel: "noopener" },
      h("img", { class: "preview", src: mediaUrl(post, m.poster), alt: "Prévia", loading: "lazy" }))),
    h("div", {},
      h("h3", {}, "Baixar"),
      h("div", { class: "row" }, m.images.map(dl)),
      h("p", { class: "muted" }, "9:16 → Stories, Status e TikTok/Kwai (modo foto, com música do app). 4:5 e 1:1 → feed do Instagram e do Facebook."),
    ));
}

function musicSection(post) {
  const songs = (post.gospel_suggestions || []).map((s) =>
    h("li", {}, h("span", {}, h("b", {}, s.title), " — ", s.artist),
      h("button", { class: "btn small", onclick: () => copy(`${s.title} ${s.artist}`) }, "Copiar")));
  return h("div", {},
    post.music && h("p", { class: "muted" }, `No vídeo com música: “${post.music.title}” · ${post.music.license}`),
    h("p", { style: "margin:8px 0 4px;font-weight:600" }, "Sugestões gospel para escolher no app:"),
    h("ul", { class: "songs" }, songs),
    h("p", { class: "muted" }, "Busque o nome na biblioteca de sons do TikTok/Kwai/Instagram ao postar o vídeo sem música."));
}

function publishedSection(post) {
  const grid = h("div", { class: "pub" });
  for (const [k, name] of PLATFORMS) {
    const when = post.published?.[k];
    const input = h("input", { type: "checkbox", checked: !!when });
    input.addEventListener("change", async () => {
      input.disabled = true;
      try {
        const r = await api(`/api/posts/${encodeURIComponent(post.id)}`, { method: "POST", body: { action: "published", platform: k, value: input.checked } });
        Object.assign(post, r.post);
        toast(input.checked ? `Marcado como publicado no ${name}` : "Desmarcado");
        render();
      } catch (e) { toast(e.message); input.checked = !input.checked; input.disabled = false; }
    });
    const link = post.publish_links?.[k]?.startsWith?.("http") ? post.publish_links[k] : null;
    const note = !link && post.publish_links?.[k];
    const err = post.publish_errors?.[k];
    grid.append(h("label", {}, input, h("span", {}, name,
      h("small", {}, when ? new Date(when).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "não publicado"),
      link && h("small", {}, h("a", { href: link, target: "_blank", rel: "noopener" }, "ver post ↗")),
      note && h("small", {}, `📥 ${note} — abra o TikTok e finalize`),
      err && h("small", { style: "color:var(--bad)" }, `erro (${err.attempts}x): ${err.message}`))));
  }
  return grid;
}

function editForm(post, card) {
  const f = h("form", { class: "stack" });
  const fields = {};
  if (post.type === "verse") {
    f.append(h("p", { class: "muted" }, `Versículo (não editável, vem da Bíblia): ${post.content.ref_label}`));
    fields.on_screen = h("input", { type: "text", maxlength: 110, value: post.content.on_screen });
    fields.reflection = h("textarea", {}, post.content.reflection);
    f.append(h("label", {}, "Frase de reflexão (aparece no vídeo)", fields.on_screen),
      h("label", {}, "Reflexão (legenda base)", fields.reflection));
  } else if (post.type === "curiosity") {
    f.append(h("p", { class: "muted" }, `Referência (não editável): ${post.content.ref_label}`));
    fields.title = h("input", { type: "text", maxlength: 60, value: post.content.title });
    fields.text = h("textarea", {}, post.content.text);
    f.append(h("label", {}, "Título (aparece na imagem)", fields.title),
      h("label", {}, "Texto (aparece na imagem)", fields.text));
  } else {
    fields.question = h("textarea", { maxlength: 140, style: "min-height:70px" }, post.content.question);
    f.append(h("label", {}, "Pergunta", fields.question));
    fields.options = post.content.options.map((o, i) => {
      const inp = h("input", { type: "text", maxlength: 48, value: o });
      f.append(h("label", {}, `Alternativa ${"ABCD"[i]}`, inp));
      return inp;
    });
    fields.answer = h("select", {}, ["A", "B", "C", "D"].map((l, i) => h("option", { value: i, selected: i === post.content.answer }, l)));
    f.append(h("label", {}, "Resposta certa", fields.answer),
      h("p", { class: "muted" }, `A resposta precisa estar no texto de ${post.content.ref_label}, senão a edição é recusada.`));
  }
  const caps = {};
  for (const [k, name] of PLATFORMS) {
    if (k === "youtube") {
      caps.yt_title = h("input", { type: "text", maxlength: 100, value: post.captions.youtube.title });
      caps.yt_desc = h("textarea", {}, post.captions.youtube.description);
      f.append(h("label", {}, "YouTube: título", caps.yt_title), h("label", {}, "YouTube: descrição", caps.yt_desc));
    } else {
      caps[k] = h("textarea", {}, post.captions[k]);
      f.append(h("label", {}, `Legenda ${name}`, caps[k]));
    }
  }
  const save = h("button", { class: "btn primary" }, "Salvar");
  f.append(h("div", { class: "row" }, save, h("button", { class: "btn", type: "button", onclick: () => render() }, "Cancelar")));
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    save.disabled = true;
    const content = post.type === "verse"
      ? { on_screen: fields.on_screen.value, reflection: fields.reflection.value }
      : post.type === "curiosity"
        ? { title: fields.title.value, text: fields.text.value }
        : { question: fields.question.value, options: fields.options.map((i) => i.value), answer: Number(fields.answer.value) };
    const captions = {
      instagram: caps.instagram.value, facebook: caps.facebook.value, tiktok: caps.tiktok.value, kwai: caps.kwai.value,
      youtube: { title: caps.yt_title.value, description: caps.yt_desc.value },
    };
    try {
      const r = await api(`/api/posts/${encodeURIComponent(post.id)}`, { method: "POST", body: { action: "edit", content, captions } });
      Object.assign(post, r.post);
      toast(r.rerender ? "Salvo! O vídeo está sendo refeito (~3 min)." : "Legendas salvas!");
      render();
    } catch (err) { toast(err.message); save.disabled = false; }
  });
  card.replaceChildren(h("div", { class: "sec" }, h("h3", {}, `Editar · ${fmtDate(post)}`), f));
}

// Redes ligadas em Configurações onde este post ainda não saiu.
function pendingNets(post) {
  const on = Object.entries(STATE.settings?.publishing || {}).filter(([, v]) => v === true).map(([k]) => k)
    .filter((k) => k !== "tiktok" || post.media?.video_silent);
  return on.filter((k) => !post.published?.[k] && (k !== "youtube" || post.media?.video_music));
}

async function publishNow(post) {
  const nets = pendingNets(post);
  if (!confirm(`Publicar agora em: ${nets.join(", ")}?`)) return;
  try {
    const r = await api(`/api/posts/${encodeURIComponent(post.id)}`, { method: "POST", body: { action: "publish_now" } });
    Object.assign(post, r.post);
    toast("Publicando! Leva cerca de 1 minuto. A tela atualiza sozinha.");
    render();
    watchPublishing(post.id, nets);
  } catch (e) { toast(e.message); }
}

// Atualiza a tela a cada 10 s até o post sair (ou dar erro), por até 4 minutos.
async function watchPublishing(id, nets) {
  for (let i = 0; i < 24; i++) {
    await new Promise((r) => setTimeout(r, 10000));
    try {
      STATE = await api("/api/state");
    } catch { continue; }
    const p = STATE.posts.find((x) => x.id === id);
    if (!p) {  // saiu em todas as redes: foi para o Histórico
      render();
      toast(`✅ Publicado em: ${nets.join(", ")}. O post saiu da fila (veja no Histórico).`);
      return;
    }
    const done = nets.every((k) => p.published?.[k] || p.publish_errors?.[k]);
    if (done || !p.publishing_now) {
      render();
      const ok = nets.filter((k) => p.published?.[k]);
      const bad = nets.filter((k) => p.publish_errors?.[k]);
      toast(bad.length ? `Publicado em: ${ok.join(", ") || "nenhuma"} · erro em: ${bad.join(", ")}` : `✅ Publicado em: ${ok.join(", ")}`);
      return;
    }
  }
  render();
}

async function setStatus(post, action) {
  try {
    const r = await api(`/api/posts/${encodeURIComponent(post.id)}`, { method: "POST", body: { action } });
    Object.assign(post, r.post);
    const auto = Object.entries(STATE.settings?.publishing || {}).filter(([k, v]) => v === true).map(([k]) => k);
    toast(action === "approve"
      ? (auto.length ? `Aprovado! Será publicado em ${auto.join(", ")} no horário (${post.time}).` : "Aprovado!")
      : action === "reject" ? "Rejeitado" : "Atualizado");
    render();
  } catch (e) { toast(e.message); }
}

function postCard(post) {
  const card = h("article", { class: "card" });
  const head = h("div", { class: "card-h" },
    h("span", { class: "when" }, fmtDate(post)),
    h("span", { class: "chip" }, TYPE_NAME[post.type] || post.type),
    h("span", { class: `chip ${post.status}` }, STATUS_NAME[post.status] || post.status));
  const alerts = [];
  if (post.error) alerts.push(h("div", { class: "alert bad" }, post.error));
  if (post.needs_render) alerts.push(h("div", { class: "alert warn" }, "Refazendo o vídeo com a sua edição… atualize a página em alguns minutos."));
  const actions = h("div", { class: "row" },
    post.status !== "approved" && h("button", { class: "btn ok", onclick: () => setStatus(post, "approve") }, "✓ Aprovar"),
    post.status !== "rejected" && h("button", { class: "btn bad", onclick: () => setStatus(post, "reject") }, "Rejeitar"),
    post.status !== "pending" && h("button", { class: "btn", onclick: () => setStatus(post, "pending") }, "Voltar p/ revisão"),
    pendingNets(post).length > 0 && h("button", { class: "btn primary", onclick: () => publishNow(post) },
      post.publishing_now && Date.now() - Date.parse(post.publishing_now) < 5 * 60e3 ? "⏳ Publicando…" : "🚀 Publicar agora"),
    h("button", { class: "btn", onclick: () => editForm(post, card) }, "✎ Editar"));
  const origin = post.source === "groq" ? `gerado pela IA (${post.model})` : `banco (${post.bank_id})`;
  card.append(head,
    h("div", { class: "sec" }, alerts, h("p", { style: "margin:0 0 4px;font-weight:600" }, titleOf(post)),
      h("p", { class: "muted", style: "margin:0 0 10px" }, `Conteúdo: ${origin} · legenda: ${post.caption_source === "groq" ? "IA" : "modelo"}`), actions),
    h("div", { class: "sec" }, mediaSection(post)),
    h("div", { class: "sec" }, h("h3", {}, "Legendas por rede"), captionBox(post)),
    h("div", { class: "sec" }, h("h3", {}, "Música"), musicSection(post)),
    h("div", { class: "sec" }, h("h3", {}, "Onde já publiquei"), publishedSection(post)));
  return card;
}

function renderQueue(main) {
  const posts = STATE.posts.filter((p) => p.status !== "rejected" || Object.values(p.published || {}).some(Boolean));
  const rejected = STATE.posts.length - posts.length;
  if (!STATE.posts.length) {
    main.append(h("div", { class: "empty" }, h("p", {}, "Nenhum post ainda."),
      h("p", {}, "Toque em “Gerar agora” ou aguarde a geração automática diária.")));
    return;
  }
  for (const p of posts) main.append(postCard(p));
  if (rejected) main.append(h("p", { class: "muted" },
    `${rejected} post(s) rejeitado(s) ocultos. Toque em “Gerar agora” para criar novos no lugar (leva uns 4 minutos).`));
}

// ---------- histórico
async function renderHistory(main) {
  const table = h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Data"), h("th", {}, "Post"),
    ...PLATFORMS.map(([, n]) => h("th", {}, n.slice(0, 2))))));
  const tbody = h("tbody");
  table.append(tbody);
  main.append(h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, "Publicações por rede"),
    h("div", { style: "overflow-x:auto" }, table))));
  let older = [];
  try { older = (await api("/api/history")).posts; } catch (e) { toast(e.message); }
  const all = [...STATE.posts, ...older].filter((p) => Object.values(p.published || {}).some(Boolean));
  if (!all.length) tbody.append(h("tr", {}, h("td", { colspan: 7, class: "muted" }, "Nada publicado ainda. Marque as redes em cada post da fila.")));
  for (const p of all) {
    tbody.append(h("tr", {}, h("td", { class: "p" }, p.date.split("-").reverse().join("/")),
      h("td", {}, h("div", {}, titleOf(p)), h("div", { class: "muted" }, TYPE_NAME[p.type])),
      ...PLATFORMS.map(([k]) => {
        const link = p.publish_links?.[k];
        const mark = p.published?.[k]
          ? (link?.startsWith?.("http") ? h("a", { href: link, target: "_blank", rel: "noopener", title: "ver post" }, "✅↗") : "✅")
          : "—";
        return h("td", { title: p.published?.[k] || "" }, mark);
      })));
  }
  const counts = PLATFORMS.map(([k, n]) => `${n}: ${all.filter((p) => p.published?.[k]).length}`).join(" · ");
  main.append(h("p", { class: "muted" }, `Total publicado — ${counts}`));
}

// ---------- configurações
function renderConfig(main) {
  const s = STATE.settings || {};
  const slots = s.schedule?.slots || [];
  const f = h("form", { class: "stack" });
  const name = h("input", { type: "text", value: s.brand?.name || "" });
  const handle = h("input", { type: "text", value: s.brand?.handle || "", placeholder: "@seuperfil" });
  const slotBox = h("div", { class: "stack" });
  const slotRows = [];
  const addSlot = (slot) => {
    if (slotRows.length >= 8) return toast("Máximo de 8 posts por dia");
    const time = h("input", { type: "time", value: slot?.time || "12:00" });
    const type = h("select", {}, Object.entries(TYPE_NAME).map(([k, n]) =>
      h("option", { value: k, selected: (slot?.type || "verse") === k }, n)));
    const row = { time, type };
    const remove = h("button", { type: "button", class: "btn small bad", onclick: () => {
      if (slotRows.length <= 1) return toast("Deixe pelo menos 1 post por dia");
      slotRows.splice(slotRows.indexOf(row), 1); line.remove();
    } }, "✕");
    const line = h("div", { class: "row" }, time, type, remove);
    slotRows.push(row);
    slotBox.append(line);
  };
  (slots.length ? slots : [{ time: "07:00", type: "verse" }]).forEach(addSlot);
  const auto = h("input", { type: "checkbox", checked: !!s.approval?.auto_approve });
  const pubBoxes = Object.fromEntries(["instagram", "facebook", "youtube", "tiktok"].map((k) =>
    [k, h("input", { type: "checkbox", checked: !!s.publishing?.[k] })]));
  const groqOn = h("input", { type: "checkbox", checked: s.groq?.enabled !== false });
  const model = h("input", { type: "text", value: s.groq?.model || "" });
  const calls = h("input", { type: "number", min: 0, max: 50, value: s.groq?.max_calls_per_day ?? 6 });
  const ratio = h("input", { type: "number", min: 0, max: 1, step: 0.1, value: s.groq?.new_content_ratio ?? 0.3 });
  f.append(
    h("label", {}, "Nome da página", name),
    h("label", {}, "Seu @ (marca d'água nos vídeos e imagens)", handle),
    h("h3", {}, "Posts por dia (horários sugeridos para postar)"),
    slotBox,
    h("button", { type: "button", class: "btn small", onclick: () => addSlot() }, "+ Adicionar horário"),
    h("p", { class: "muted" }, "Os posts do dia são gerados de madrugada (05:17). Com a publicação automática ligada, cada post aprovado sai no horário dele (até ~7 min depois). Use horários cheios (ex.: 12:00)."),
    h("label", { class: "check" }, auto, "Aprovar automaticamente (sem revisão)"),
    h("h3", {}, "Publicação automática (ao aprovar, no horário do post)"),
    h("label", { class: "check" }, pubBoxes.instagram, "Instagram (versículo no feed, quiz no Reels)"),
    h("label", { class: "check" }, pubBoxes.facebook, "Facebook (Página)"),
    h("label", { class: "check" }, pubBoxes.youtube, "YouTube Shorts (quiz; fica privado até a auditoria do YouTube)"),
    h("label", { class: "check" }, pubBoxes.tiktok, "TikTok (Reels vão para os rascunhos do app: você escolhe a música e publica)"),
    h("div", { class: "row" },
      STATE.tiktok?.connected
        ? h("span", { class: "muted" }, `TikTok conectado${STATE.tiktok.name ? `: ${STATE.tiktok.name}` : ""} ✔`)
        : h("span", { class: "muted" }, "TikTok não conectado."),
      h("a", { class: "btn small", href: "/api/tiktok/connect" }, STATE.tiktok?.connected ? "Reconectar TikTok" : "Conectar TikTok")),
    h("p", { class: "muted" }, "Kwai continua manual. Cada rede precisa das chaves configuradas (veja docs/PUBLICACAO.md e docs/TIKTOK.md)."),
    h("h3", {}, "Inteligência artificial (Groq)"),
    h("label", { class: "check" }, groqOn, "Usar a Groq para conteúdo novo e variações de legenda"),
    h("label", {}, "Modelo", model),
    h("label", {}, "Máximo de chamadas por dia", calls),
    h("label", {}, "Chance de conteúdo novo pela IA (0 a 1)", ratio),
    h("p", { class: "muted" }, `Uso hoje: ${STATE.groq?.date === new Date().toISOString().slice(0, 10) ? STATE.groq.calls : 0} chamada(s).`),
  );
  const save = h("button", { class: "btn primary" }, "Salvar configurações");
  f.append(save);
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    save.disabled = true;
    try {
      const r = await api("/api/settings", { method: "PUT", body: {
        name: name.value, handle: handle.value,
        slots: slotRows.map((r) => ({ time: r.time.value, type: r.type.value }))
          .sort((a, b) => a.time.localeCompare(b.time)),
        auto_approve: auto.checked, groq_enabled: groqOn.checked, model: model.value.trim(),
        publishing: Object.fromEntries(Object.entries(pubBoxes).map(([k, b]) => [k, b.checked])),
        max_calls_per_day: Number(calls.value), new_content_ratio: Number(ratio.value),
      } });
      STATE.settings = r.settings;
      toast("Configurações salvas! Valem a partir da próxima geração.");
    } catch (err) { toast(err.message); }
    save.disabled = false;
  });
  main.append(h("div", { class: "card" }, h("div", { class: "sec" }, f)));
}

// ---------- geral
function render() {
  const main = document.getElementById("main");
  main.replaceChildren();
  document.getElementById("brand").textContent = STATE.settings?.brand?.name || "Painel";
  if (TAB === "fila") renderQueue(main);
  else if (TAB === "historico") renderHistory(main);
  else renderConfig(main);
}

async function load() {
  try {
    STATE = await api("/api/state");
    render();
  } catch (e) {
    if (e.message !== "login") document.getElementById("main").replaceChildren(h("div", { class: "alert bad" }, e.message));
  }
}

document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => {
  TAB = b.dataset.tab;
  document.querySelectorAll("nav button").forEach((x) => x.classList.toggle("on", x === b));
  render();
}));
document.getElementById("gen").addEventListener("click", async (e) => {
  const n = STATE.settings?.schedule?.slots?.length || 0;
  if (!confirm(`Apagar os posts atuais da fila e gerar ${n} novos para hoje?\n\nOs que já foram publicados continuam no Histórico. Posts cujo horário já passou ficam aguardando você (use “Publicar agora”).`)) return;
  e.target.disabled = true;
  try { await api("/api/generate", { method: "POST", body: { clear: true } }); toast("Gerando posts novos! Leva uns 4–6 minutos. Atualize depois."); }
  catch (err) { toast(err.message); }
  e.target.disabled = false;
});
document.getElementById("logout").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  location.href = "/login";
});
load();
