"use strict";
// Painel: fila de posts, pré-visualização, download, legendas e histórico.

const PLATFORMS = [
  ["instagram", "Instagram"], ["facebook", "Facebook"], ["tiktok", "TikTok"],
  ["kwai", "Kwai"], ["youtube", "YouTube"],
];
const TYPE_NAME = { verse: "Versículo do dia", quiz: "Desafio de quiz" };
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
  return post.type === "verse" ? post.content.ref_label : post.content.question;
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
    const link = post.publish_links?.[k];
    const err = post.publish_errors?.[k];
    grid.append(h("label", {}, input, h("span", {}, name,
      h("small", {}, when ? new Date(when).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "não publicado"),
      link && h("small", {}, h("a", { href: link, target: "_blank", rel: "noopener" }, "ver post ↗")),
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
      ...PLATFORMS.map(([k]) => h("td", { title: p.published?.[k] || "" }, p.published?.[k] ? "✅" : "—"))));
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
  const slotRows = [0, 1].map((i) => {
    const on = h("input", { type: "checkbox", checked: i < slots.length, disabled: i === 0 });
    const time = h("input", { type: "time", value: slots[i]?.time || (i ? "19:00" : "07:00") });
    const type = h("select", {}, Object.entries(TYPE_NAME).map(([k, n]) =>
      h("option", { value: k, selected: (slots[i]?.type || (i ? "quiz" : "verse")) === k }, n)));
    return { on, time, type };
  });
  const auto = h("input", { type: "checkbox", checked: !!s.approval?.auto_approve });
  const pubBoxes = Object.fromEntries(["instagram", "facebook", "youtube"].map((k) =>
    [k, h("input", { type: "checkbox", checked: !!s.publishing?.[k] })]));
  const groqOn = h("input", { type: "checkbox", checked: s.groq?.enabled !== false });
  const model = h("input", { type: "text", value: s.groq?.model || "" });
  const calls = h("input", { type: "number", min: 0, max: 50, value: s.groq?.max_calls_per_day ?? 6 });
  const ratio = h("input", { type: "number", min: 0, max: 1, step: 0.1, value: s.groq?.new_content_ratio ?? 0.3 });
  f.append(
    h("label", {}, "Nome da página", name),
    h("label", {}, "Seu @ (marca d'água nos vídeos e imagens)", handle),
    h("h3", {}, "Posts por dia (horários sugeridos para postar)"),
    slotRows.map((r, i) => h("div", { class: "row" }, h("label", { class: "check" }, r.on, `Post ${i + 1}`), r.time, r.type)),
    h("p", { class: "muted" }, "Os posts são gerados uma vez por dia de madrugada. Os horários acima aparecem na fila como sugestão de quando postar (e serão usados pela publicação automática nas próximas fases)."),
    h("label", { class: "check" }, auto, "Aprovar automaticamente (sem revisão)"),
    h("h3", {}, "Publicação automática (ao aprovar, no horário do post)"),
    h("label", { class: "check" }, pubBoxes.instagram, "Instagram (versículo no feed, quiz no Reels)"),
    h("label", { class: "check" }, pubBoxes.facebook, "Facebook (Página)"),
    h("label", { class: "check" }, pubBoxes.youtube, "YouTube Shorts (quiz; fica privado até a auditoria do YouTube)"),
    h("p", { class: "muted" }, "TikTok e Kwai continuam manuais. Cada rede precisa das chaves configuradas (veja docs/PUBLICACAO.md)."),
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
        slots: slotRows.filter((r) => r.on.checked).map((r) => ({ time: r.time.value, type: r.type.value })),
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
  if (!confirm("Gerar os posts de hoje agora? Os que você rejeitou serão substituídos por novos.")) return;
  e.target.disabled = true;
  try { await api("/api/generate", { method: "POST", body: {} }); toast("Gerando! Leva uns 3–5 minutos. Atualize depois."); }
  catch (err) { toast(err.message); }
  e.target.disabled = false;
});
document.getElementById("logout").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  location.href = "/login";
});
load();
