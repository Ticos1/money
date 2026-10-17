"use strict";
// Painel: hoje (saúde do sistema), fila de posts, agenda, histórico, métricas e configurações.

const PLATFORMS = [
  ["instagram", "Instagram"], ["facebook", "Facebook"], ["tiktok", "TikTok"],
  ["kwai", "Kwai"], ["youtube", "YouTube"], ["whatsapp", "Canal WhatsApp"],
];
// redes de publicação (as legendas usam PLATFORMS; Stories não tem legenda)
const NETS = [...PLATFORMS, ["stories", "Stories IG"]];
const TYPE_NAME = { verse: "Versículo do dia", quiz: "Desafio de quiz (Reels)", curiosity: "Você sabia?",
  fill: "Complete o versículo (Reels)", truefalse: "Verdadeiro ou falso (Reels)",
  book: "Em qual livro está? (Reels)" };
const LONG_NAME = "Vídeo longo de quiz (YouTube)";
const WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
const typeName = (t) => (t === "compilation" ? LONG_NAME : TYPE_NAME[t] || t);
const STATUS_NAME = { pending: "Aguardando aprovação", approved: "Aprovado", rejected: "Rejeitado" };
const IMG_NAME = {
  "imagem_quadrada.jpg": "Imagem 1:1", "imagem_vertical.jpg": "Imagem 4:5", "imagem_story.jpg": "Imagem 9:16",
  "pergunta_quadrada.jpg": "Pergunta 1:1", "pergunta_vertical.jpg": "Pergunta 4:5",
  "resposta_quadrada.jpg": "Resposta 1:1", "resposta_vertical.jpg": "Resposta 4:5",
  "carrossel_1.jpg": "Carrossel 1/4", "carrossel_2.jpg": "Carrossel 2/4",
  "carrossel_3.jpg": "Carrossel 3/4", "carrossel_4.jpg": "Carrossel 4/4",
};

const NET_SHORT = { instagram: "IG", facebook: "FB", youtube: "YT", stories: "ST", tiktok: "TT", kwai: "KW", whatsapp: "WA" };
const NET_NAME = Object.fromEntries(NETS);
const AUTO_NETS = ["instagram", "facebook", "youtube", "stories", "tiktok"]; // publicação automática
const VIDEO_KINDS = ["quiz", "fill", "truefalse", "book"]; // sempre em vídeo (app/generate.py)
const POLL_MS = 40000; // atualização automática enquanto algo está rodando

let STATE = { posts: [], settings: {} };
let TAB = "hoje";
let RUNS = { pipeline: null, publish: null }; // execuções do GitHub Actions em andamento
let EDITING = false; // formulário de edição aberto: a atualização automática não redesenha a tela

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
  return `${day} · ${postTime(post)}`;
}

// horário real de saída (o do slot ± alguns minutos, para não parecer automação)
function postTime(post) {
  return post.publish_at?.slice(11, 16) || post.time;
}

// data/hora no fuso do painel (config timezone, padrão Brasília)
const TZ = () => STATE.settings?.timezone || "America/Sao_Paulo";
function dayOf(at) { return new Intl.DateTimeFormat("en-CA", { timeZone: TZ() }).format(at ? new Date(at) : new Date()); }
function clock(at) { return new Date(at).toLocaleTimeString("pt-BR", { timeZone: TZ(), hour: "2-digit", minute: "2-digit" }); }
function nowLocal() {
  const t = new Intl.DateTimeFormat("en-GB", { timeZone: TZ(), hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date());
  return `${dayOf()} ${t}`;
}
const dueAt = (post) => (post.publish_at || `${post.date}T${post.time}`).replace("T", " ");
const ddmm = (d) => d.split("-").reverse().slice(0, 2).join("/");

// A rede recebe este post? (mesmas regras de app/publish.py e dashboard/lib/rules.js)
function appliesNet(k, post, pub = STATE.settings?.publishing || {}) {
  if (Array.isArray(pub[`${k}_types`]) && !pub[`${k}_types`].includes(post.type)) return false;
  if (post.type === "compilation") return k === "youtube" && !!post.media?.video_music;
  if (Array.isArray(pub[`${k}_times`]) && !pub[`${k}_times`].includes(post.time)) return false;
  if (k === "youtube") return !!post.media?.video_music;
  if (k === "tiktok") return !!post.media?.video_silent;
  if (k === "stories") return !!(post.media?.video_music || post.media?.images?.includes("imagem_story.jpg"));
  return true;
}
const autoNets = (post) => AUTO_NETS.filter((k) => STATE.settings?.publishing?.[k] && appliesNet(k, post));
const paused = () => !!STATE.settings?.publishing?.paused;

// ✅ publicado · ⏭ pulado · ❌ erro · ⏳ aguardando
function netStatus(post, k) {
  if (post.published?.[k]) return { icon: "✅", text: "publicado", cls: "ok" };
  if (post.publish_skipped?.[k]) return { icon: "⏭", text: post.publish_skipped[k], cls: "skip" };
  if (post.publish_errors?.[k]) return { icon: "❌", text: `erro (${post.publish_errors[k].attempts}x): ${post.publish_errors[k].message}`, cls: "bad" };
  return { icon: "⏳", text: "aguardando", cls: "wait" };
}

function titleOf(post) {
  if (post.title) return post.title; // vindo do histórico paginado (já resumido)
  if (post.type === "compilation") return post.content.title;
  if (post.type === "fill") return `Complete: ${post.content.ref_label}`;
  if (post.type === "book") return `Em qual livro? ${post.content.ref_label}`;
  if (post.type === "truefalse") return `${post.content.question} → ${post.content.shown}?`;
  if (post.type === "verse") return post.content.ref_label;
  if (post.type === "curiosity") return post.content.title;
  return post.content.question;
}

// ---------- fila
// Canal do WhatsApp não tem API: o painel entrega mídia + legenda pelo "Compartilhar" do celular.
function whatsappMedia(post) {
  const m = post.media || {};
  if (m.video_music) return m.video_music; // canal não tem biblioteca de músicas
  return (m.images || []).find((f) => f === "imagem_vertical.jpg") || (m.images || [])[0] || m.poster;
}

function whatsappButton(post, text) {
  let file = null;
  const btn = h("button", { class: "btn small", onclick: async () => {
    await copy(text);
    const name = whatsappMedia(post);
    try {
      if (!file && name) {
        btn.textContent = "⏳ Preparando…";
        const res = await fetch(mediaUrl(post, name));
        if (!res.ok) throw new Error("falha ao baixar a mídia");
        const blob = await res.blob();
        file = new File([blob], `${post.id}-${name}`, { type: blob.type || (name.endsWith(".mp4") ? "video/mp4" : "image/jpeg") });
      }
      const data = file ? { files: [file], text } : { text };
      if (!navigator.share || (navigator.canShare && !navigator.canShare(data))) {
        toast("Este navegador não envia arquivos. Legenda copiada: baixe a mídia acima e poste no canal.");
        btn.textContent = "📲 Enviar no canal";
        return;
      }
      await navigator.share(data);
      btn.textContent = "📲 Enviar no canal";
    } catch (e) {
      // o download demorou e o navegador exigiu um novo toque
      btn.textContent = e.name === "NotAllowedError" ? "📲 Pronto! Toque de novo" : "📲 Enviar no canal";
      if (e.name !== "AbortError" && e.name !== "NotAllowedError") toast(e.message);
    }
  } }, "📲 Enviar no canal");
  return btn;
}

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
      if (key === "whatsapp") body.append(" ", whatsappButton(post, text),
        h("p", { class: "muted" }, "Abre o WhatsApp com a mídia e a legenda: escolha o seu canal na lista. Se a legenda não vier junto, ela já está copiada: é só colar."));
    }
  };
  for (const [k, name] of PLATFORMS) {
    if (k === "youtube" && !post.media?.video_music) continue; // Shorts precisa de vídeo
    if (k === "whatsapp" && !post.captions?.whatsapp) continue; // posts antigos não têm
    if (post.type === "compilation" && k !== "youtube") continue; // vídeo longo: só YouTube
    tabs.append(h("button", { "data-k": k, onclick: () => show(k) }, name));
  }
  box.append(tabs, body);
  show(post.type === "compilation" ? "youtube" : "instagram");
  return box;
}

function longVideoSection(post) {
  const m = post.media, c = post.content;
  const video = h("video", { class: "preview wide", controls: true, playsinline: true, preload: "none",
    poster: mediaUrl(post, m.poster), src: mediaUrl(post, m.video_music) });
  const mins = Math.floor((m.duration || 0) / 60), secs = Math.round((m.duration || 0) % 60);
  const dl = (file, label) => h("a", { class: "btn small", href: mediaUrl(post, file), download: `${post.id}-${file}` }, `⬇ ${label}`);
  const list = h("details", {}, h("summary", {}, `Ver as ${c.count} perguntas`),
    h("ol", { class: "songs" }, (c.questions || []).map((q) => h("li", {}, h("span", {}, q.question, " ", h("span", { class: "muted" }, `(${q.ref_label})`))))));
  return h("div", { class: "media" },
    h("div", {}, video),
    h("div", {},
      h("h3", {}, "Vídeo longo de quiz"),
      h("p", { class: "muted" }, `${c.count} perguntas · ${mins}min${String(secs).padStart(2, "0")}s · 16:9 · sai só no YouTube (não é Short), com miniatura e capítulos.`),
      h("div", { class: "row" }, dl(m.video_music, "Vídeo"), dl(m.thumbnail || m.poster, "Miniatura")),
      list));
}

function mediaSection(post) {
  if (!post.media || !post.media.base) return h("p", { class: "muted" }, "Sem mídia (post antigo).");
  const m = post.media;
  if (post.type === "compilation") return longVideoSection(post);
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
      h("div", { class: "row" }, dl(m.video_music, "Vídeo com música"), dl(m.video_silent, "Vídeo sem música"),
        m.thumbnail ? dl(m.thumbnail, "Capa do YouTube") : null),
      h("p", { class: "muted" }, "Com música → YouTube, Facebook (e Instagram, se quiser). Sem música → TikTok, Kwai e Instagram, escolhendo a música no próprio app."),
      m.thumbnail ? h("p", { class: "muted" }, "Capa do YouTube: texto grande para o Short. A publicação automática já tenta aplicar; se não pegar, troque no app do YouTube ou no YouTube Studio.") : null,
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
      h("p", { class: "muted" }, "9:16 → Stories, Status e TikTok/Kwai (modo foto, com música do app). 4:5 e 1:1 → feed do Instagram e do Facebook. Carrossel 1 a 4 → Instagram (poste as 4 juntas, nessa ordem)."),
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
  for (const [k, name] of NETS) {
    if (post.type === "compilation" && k !== "youtube") continue;
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
    const skipped = post.publish_skipped?.[k];
    grid.append(h("label", {}, input, h("span", {}, name,
      h("small", {}, when ? new Date(when).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "não publicado"),
      link && h("small", {}, h("a", { href: link, target: "_blank", rel: "noopener" }, "ver post ↗")),
      note && h("small", {}, `📥 ${note} — abra o TikTok e finalize`),
      skipped && h("small", { class: "muted" }, `⏭ ${skipped}`),
      err && h("small", { style: "color:var(--bad)" }, `erro (${err.attempts}x): ${err.message}`))));
  }
  return grid;
}

function editLongForm(post, card) {
  EDITING = true;
  const f = h("form", { class: "stack" });
  const title = h("input", { type: "text", maxlength: 100, value: post.captions.youtube.title });
  const desc = h("textarea", { style: "min-height:240px" }, post.captions.youtube.description);
  const save = h("button", { class: "btn primary" }, "Salvar");
  f.append(h("label", {}, "YouTube: título", title), h("label", {}, "YouTube: descrição (mantenha os capítulos 0:00, 0:07...)", desc),
    h("div", { class: "row" }, save, h("button", { class: "btn", type: "button", onclick: () => render() }, "Cancelar")));
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    save.disabled = true;
    try {
      const r = await api(`/api/posts/${encodeURIComponent(post.id)}`, { method: "POST",
        body: { action: "edit", captions: { youtube: { title: title.value, description: desc.value } } } });
      Object.assign(post, r.post);
      toast("Salvo!");
      render();
    } catch (err) { toast(err.message); save.disabled = false; }
  });
  card.replaceChildren(h("div", { class: "sec" }, h("h3", {}, `Editar · ${fmtDate(post)}`), f));
}

function editForm(post, card) {
  EDITING = true;
  if (post.type === "compilation") return editLongForm(post, card);
  const f = h("form", { class: "stack" });
  const fields = {};
  if (post.type === "verse") {
    f.append(h("p", { class: "muted" }, `Versículo (não editável, vem da Bíblia): ${post.content.ref_label}`));
    fields.on_screen = h("input", { type: "text", maxlength: 110, value: post.content.on_screen });
    fields.reflection = h("textarea", {}, post.content.reflection);
    fields.application = h("textarea", { maxlength: 240, style: "min-height:70px" }, post.content.application || "");
    f.append(h("label", {}, "Frase de reflexão (aparece no vídeo e no carrossel)", fields.on_screen),
      h("label", {}, "Reflexão (legenda base e carrossel)", fields.reflection),
      h("label", {}, "Aplicação prática (slide 3 do carrossel; vazio = frase padrão)", fields.application));
  } else if (post.type === "curiosity") {
    f.append(h("p", { class: "muted" }, `Referência (não editável): ${post.content.ref_label}`));
    fields.title = h("input", { type: "text", maxlength: 60, value: post.content.title });
    fields.text = h("textarea", {}, post.content.text);
    f.append(h("label", {}, "Título (aparece na imagem)", fields.title),
      h("label", {}, "Texto (aparece na imagem)", fields.text));
  } else if (["fill", "truefalse", "book"].includes(post.type)) {
    f.append(h("p", { class: "muted" }, `Este vídeo é montado automaticamente a partir do banco já conferido na Bíblia (${post.content.ref_label}). Aqui dá para editar só as legendas.`));
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
    const content = ["fill", "truefalse", "book"].includes(post.type) ? {} : post.type === "verse"
      ? { on_screen: fields.on_screen.value, reflection: fields.reflection.value, application: fields.application.value }
      : post.type === "curiosity"
        ? { title: fields.title.value, text: fields.text.value }
        : { question: fields.question.value, options: fields.options.map((i) => i.value), answer: Number(fields.answer.value) };
    const captions = {
      instagram: caps.instagram.value, facebook: caps.facebook.value, tiktok: caps.tiktok.value, kwai: caps.kwai.value,
      whatsapp: caps.whatsapp.value,
      youtube: { title: caps.yt_title.value, description: caps.yt_desc.value },
    };
    try {
      const r = await api(`/api/posts/${encodeURIComponent(post.id)}`, { method: "POST", body: { action: "edit", content, captions } });
      Object.assign(post, r.post);
      toast(r.rerender ? "Salvo! O vídeo está sendo refeito (~3 min). A tela atualiza sozinha." : "Legendas salvas!");
      render();
      if (r.rerender) kickPoll();
    } catch (err) { toast(err.message); save.disabled = false; }
  });
  card.replaceChildren(h("div", { class: "sec" }, h("h3", {}, `Editar · ${fmtDate(post)}`), f));
}

// Redes ligadas em Configurações onde este post ainda não saiu.
function pendingNets(post) {
  return autoNets(post).filter((k) => !post.published?.[k] && !post.publish_skipped?.[k]);
}

async function publishNow(post) {
  const nets = pendingNets(post);
  if (!confirm(`Publicar agora em: ${nets.join(", ")}?`)) return;
  try {
    const r = await api(`/api/posts/${encodeURIComponent(post.id)}`, { method: "POST", body: { action: "publish_now" } });
    Object.assign(post, r.post);
    toast("Publicando! Leva cerca de 1 minuto. A tela atualiza sozinha.");
    render();
    kickPoll();
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
    const auto = autoNets(post).map((k) => NET_NAME[k]);
    toast(action === "approve"
      ? (paused() ? "Aprovado! As publicações estão pausadas: sai quando você retomar."
        : auto.length ? `Aprovado! Será publicado em ${auto.join(", ")} no horário (${postTime(post)}).` : "Aprovado!")
      : action === "reject" ? "Rejeitado" : "Atualizado");
    render();
    if (r.publishing) kickPoll();
  } catch (e) { toast(e.message); }
}

function postCard(post) {
  const card = h("article", { class: "card", id: `post-${post.id}` });
  const head = h("div", { class: "card-h" },
    h("span", { class: "when" }, fmtDate(post)),
    h("span", { class: "chip" }, typeName(post.type)),
    h("span", { class: `chip ${post.status}` }, STATUS_NAME[post.status] || post.status));
  const alerts = [];
  if (post.error) alerts.push(h("div", { class: "alert bad" }, post.error));
  if (post.needs_render) alerts.push(h("div", { class: "alert warn" }, "Refazendo o vídeo com a sua edição… (~3 min, a tela atualiza sozinha)."));
  const actions = h("div", { class: "row" },
    post.status !== "approved" && h("button", { class: "btn ok", onclick: () => setStatus(post, "approve") }, "✓ Aprovar"),
    post.status !== "rejected" && h("button", { class: "btn bad", onclick: () => setStatus(post, "reject") }, "Rejeitar"),
    post.status !== "pending" && h("button", { class: "btn", onclick: () => setStatus(post, "pending") }, "Voltar p/ revisão"),
    !paused() && pendingNets(post).length > 0 && h("button", { class: "btn primary", onclick: () => publishNow(post) },
      post.publishing_now && Date.now() - Date.parse(post.publishing_now) < 5 * 60e3 ? "⏳ Publicando…" : "🚀 Publicar agora"),
    h("button", { class: "btn", onclick: () => editForm(post, card) }, "✎ Editar"));
  const long = post.type === "compilation";
  const origin = long ? `${post.content.count} perguntas do banco e dos últimos posts`
    : post.repost_of ? `♻️ repost do melhor post da semana (${post.repost_of}), em formato novo`
    : post.source === "groq" ? `gerado pela IA (${post.model})` : `banco (${post.bank_id})`;
  card.append(head,
    h("div", { class: "sec" }, alerts, h("p", { style: "margin:0 0 4px;font-weight:600" }, titleOf(post)),
      h("p", { class: "muted", style: "margin:0 0 10px" }, long ? `Conteúdo: ${origin}` : `Conteúdo: ${origin} · legenda: ${post.caption_source === "groq" ? "IA" : "modelo"}`), actions),
    h("div", { class: "sec" }, mediaSection(post)),
    h("div", { class: "sec" }, h("h3", {}, long ? "Título e descrição (YouTube)" : "Legendas por rede"), captionBox(post)),
    ...(long ? [] : [h("div", { class: "sec" }, h("h3", {}, "Música"), musicSection(post))]),
    h("div", { class: "sec" }, h("h3", {}, "Onde já publiquei"), publishedSection(post)));
  return card;
}

function renderQueue(main) {
  const posts = STATE.posts.filter((p) => p.status !== "rejected" || Object.values(p.published || {}).some(Boolean));
  const rejected = STATE.posts.length - posts.length;
  if (!STATE.posts.length) {
    main.append(h("div", { class: "empty" }, h("p", {}, "Nenhum post ainda."),
      h("p", {}, "Aguarde a geração automática (05:20) ou use Configurações → “Gerar só o que falta”.")));
    return;
  }
  for (const p of posts) main.append(postCard(p));
  if (rejected) main.append(h("p", { class: "muted" },
    `${rejected} post(s) rejeitado(s) ocultos. Em Configurações → “Gerar só o que falta”, eles são refeitos (leva uns 4 minutos).`));
}

// ---------- hoje
const TODAY_OPEN = new Set(); // posts com o card aberto na linha do tempo
const FULL_POSTS = {}; // posts completos do histórico (abertos pela linha do tempo)

function todayPosts() {
  const today = dayOf();
  const live = STATE.posts.filter((p) => p.date === today);
  const ids = new Set(live.map((p) => p.id));
  const done = STATE.health?.date === today ? (STATE.health.today_done || []).filter((p) => !ids.has(p.id)) : [];
  return [...live, ...done.map((p) => ({ ...p, _done: true }))].sort((a, b) => dueAt(a).localeCompare(dueAt(b)));
}

function youtubeToday() {
  const today = dayOf(), seen = new Set();
  const all = [...STATE.posts, ...(STATE.health?.today_done || [])];
  return all.filter((p) => {
    if (seen.has(p.id)) return false;
    seen.add(p.id);
    return p.published?.youtube && dayOf(p.published.youtube) === today;
  }).length;
}

function meter(label, used, max, note) {
  const pct = max ? Math.min(100, Math.round((used / max) * 100)) : 0;
  const cls = used >= max ? "bad" : pct >= 80 ? "warn" : "ok";
  return h("div", { class: "stat" }, h("div", { class: "muted" }, label),
    h("div", { class: "stat-n" }, h("b", {}, used), ` / ${max}`),
    h("div", { class: "track" }, h("div", { class: `fill ${cls}`, style: `width:${pct}%` })),
    note ? h("div", { class: "muted small" }, note) : null);
}

function problemsCard() {
  const hl = STATE.health;
  const box = h("div", { class: "sec" }, h("h3", {}, "Problemas"));
  if (!hl) {
    box.append(h("p", { class: "muted" }, "Ainda sem verificação. Ela aparece depois da próxima rodada do “Publicar nas redes” (de hora em hora)."));
    return h("div", { class: "card" }, box);
  }
  const hasToday = STATE.posts.some((p) => p.date === dayOf());
  // a verificação roda de hora em hora: se os posts de hoje já chegaram, o aviso de geração é velho
  const list = (hl.problems || []).filter((p) => !(p.key === "geracao" && hasToday));
  const age = (Date.now() - Date.parse(hl.updated_at)) / 3600e3;
  if (age > 4) list.unshift({ key: "velho", message: `A verificação não roda há ${Math.floor(age)} h. Veja se o workflow “Publicar nas redes” está ativo em Actions.` });
  if (!list.length) box.append(h("p", { class: "ok-line" }, "✅ Tudo em dia: geração, publicação e tokens."));
  for (const p of list) box.append(h("div", { class: "alert bad", style: "white-space:pre-line" }, p.message));
  box.append(h("p", { class: "muted small" }, `Verificado às ${clock(hl.updated_at)}${dayOf(hl.updated_at) !== dayOf() ? ` de ${ddmm(dayOf(hl.updated_at))}` : ""}.`));
  return h("div", { class: "card" }, box);
}

function countersCard() {
  const s = STATE.settings || {};
  const groqUsed = STATE.groq?.date === dayOf() ? STATE.groq.calls : 0;
  const bank = STATE.health?.bank || [];
  const grid = h("div", { class: "stats" },
    meter("Envios ao YouTube hoje", youtubeToday(), Number(s.publishing?.youtube_max_per_day ?? 5), "cota grátis da API"),
    meter("Chamadas da Groq hoje", groqUsed, Number(s.groq?.max_calls_per_day ?? 6), s.groq?.enabled === false ? "IA desligada" : "acima disso, usa o banco"));
  const rows = bank.filter((b) => b.per_day).sort((a, b) => (a.days_left ?? 1e9) - (b.days_left ?? 1e9));
  return h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, "Contadores do dia"), grid,
    rows.length ? h("div", { style: "margin-top:12px" }, h("div", { class: "muted", style: "margin-bottom:6px" }, "Dias de banco inédito por formato"),
      h("div", { class: "bank" }, rows.map((b) => h("div", { class: `bank-i${b.warn ? " warn" : ""}` },
        h("span", {}, typeName(b.kind).replace(/ \(Reels\)$/, "")), h("b", {}, b.warn ? `⚠️ ${b.days_left}` : b.days_left ?? "—"),
        h("small", { class: "muted" }, `${b.per_day}/dia · ${b.fresh} inéditos`)))))
      : h("p", { class: "muted small" }, "Dias de banco: aparecem depois da próxima verificação.")));
}

async function openFull(post, holder) {
  if (!post._done) return holder.replaceChildren(postCard(post));
  holder.replaceChildren(h("p", { class: "muted" }, "Carregando…"));
  try {
    FULL_POSTS[post.id] ||= (await api(`/api/history?id=${encodeURIComponent(post.id)}`)).post;
    holder.replaceChildren(postCard(FULL_POSTS[post.id]));
  } catch (e) { holder.replaceChildren(h("div", { class: "alert bad" }, e.message)); }
}

function timelineCard() {
  const posts = todayPosts();
  const list = h("div", { class: "tl" });
  if (!posts.length) list.append(h("p", { class: "muted" }, "Nenhum post de hoje ainda. A geração automática roda às 05:20."));
  const now = nowLocal();
  for (const p of posts) {
    const nets = p.type === "compilation" ? ["youtube"] : (p._done ? Object.keys({ ...p.published, ...p.publish_skipped, ...p.publish_errors }).filter((k) => AUTO_NETS.includes(k)) : autoNets(p));
    const holder = h("div", { class: "tl-card" });
    const state = p.status === "rejected" ? "rejeitado" : p.status === "pending" ? "aguardando aprovação"
      : p.needs_render ? "refazendo vídeo" : p.error ? "erro na geração" : "";
    const late = !p._done && p.status === "approved" && dueAt(p) <= now && nets.some((k) => netStatus(p, k).cls === "wait");
    const row = h("button", { class: `tl-row${dueAt(p) <= now ? " past" : ""}`, "aria-expanded": TODAY_OPEN.has(p.id) ? "true" : "false", onclick: () => {
      if (TODAY_OPEN.has(p.id)) { TODAY_OPEN.delete(p.id); holder.replaceChildren(); row.setAttribute("aria-expanded", "false"); }
      else { TODAY_OPEN.add(p.id); row.setAttribute("aria-expanded", "true"); openFull(p, holder); }
    } },
      h("span", { class: "tl-time" }, postTime(p)),
      h("span", { class: "tl-what" }, h("b", {}, typeName(p.type).replace(/ \((Reels|YouTube)\)$/, "")), h("small", { class: "muted" }, titleOf(p)),
        state ? h("small", { class: p.status === "rejected" || p.error ? "bad-t" : "warn-t" }, state) : null,
        late && !paused() ? h("small", { class: "warn-t" }, "horário passou, ainda saindo") : null),
      h("span", { class: "tl-nets" }, nets.length ? nets.map((k) => {
        const st = netStatus(p, k);
        return h("span", { class: `net ${st.cls}`, title: `${NET_NAME[k]}: ${st.text}` }, NET_SHORT[k], " ", st.icon);
      }) : h("span", { class: "muted small" }, "manual")));
    list.append(h("div", {}, row, holder));
    if (TODAY_OPEN.has(p.id)) openFull(p, holder);
  }
  return h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, `Posts de hoje · ${ddmm(dayOf())}`), list,
    h("p", { class: "muted small" }, "✅ publicado · ⏳ aguardando · ❌ erro · ⏭ pulado. Toque no post para abrir o card completo.")));
}

function renderToday(main) {
  main.append(problemsCard(), timelineCard(), countersCard());
}

// ---------- agenda (próximos 7 dias)
function slotPost(type, time) {
  const video = VIDEO_KINDS.includes(type) || (STATE.settings?.video?.video_types || ["quiz"]).includes(type);
  return { type, time, media: video ? { video_music: "x", video_silent: "x" } : { images: ["imagem_story.jpg"] } };
}

function renderAgenda(main) {
  const s = STATE.settings || {};
  const today = dayOf();
  const frozen = s.schedule?.frozen_until;
  if (frozen && frozen >= today) {
    main.append(h("div", { class: "alert warn" }, `🧊 Grade congelada até ${frozen.split("-").reverse().join("/")}: horários e formatos não mudam antes disso, para os testes terem dados.`));
  }
  if (paused()) main.append(h("div", { class: "alert bad" }, "⏸ Publicações pausadas: a agenda abaixo só vale depois de retomar."));
  const specials = STATE.health?.specials || {};
  const cap = Number(s.publishing?.youtube_max_per_day ?? 5);
  const slots = s.schedule?.slots || [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(`${today}T12:00:00`);
    d.setDate(d.getDate() + i);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const pyDay = (d.getDay() + 6) % 7; // 0 = segunda, como em config/settings.json
    const items = slots.map((x) => ({ ...x, post: slotPost(x.type, x.time) }));
    const comp = s.compilation;
    if (comp?.enabled && Number(comp.weekday) === pyDay) {
      items.push({ time: comp.time, type: "compilation", extra: `Vídeo longo de ~${comp.minutes || 10} min`, post: { type: "compilation", media: { video_music: "x" } } });
    }
    const rp = s.repost;
    if (rp?.enabled && Number(rp.weekday ?? 6) === pyDay) {
      items.push({ time: rp.time || "19:15", type: "repost", extra: "♻️ Repost do melhor post da semana (em outro formato)", post: { type: "quiz", time: rp.time, media: { video_music: "x", video_silent: "x" } } });
    }
    items.sort((a, b) => a.time.localeCompare(b.time));
    const yt = items.filter((x) => autoNets(x.post).includes("youtube")).length;
    const sp = specials[iso];
    const head = h("div", { class: "card-h" },
      h("span", { class: "when" }, d.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "2-digit" }), i === 0 ? " (hoje)" : ""),
      sp ? h("span", { class: "chip special", title: sp.hook }, `🎉 ${sp.name}`) : pyDay === 6 ? h("span", { class: "chip", title: "O Versículo do dia prefere o tema de domingo (louvor, igreja)" }, "Domingo") : null);
    const list = h("div", { class: "agenda" }, items.map((x) => h("div", { class: "ag-row" },
      h("span", { class: "tl-time" }, x.time),
      h("span", {}, x.extra || typeName(x.type).replace(/ \(Reels\)$/, "")),
      h("span", { class: "tl-nets" }, autoNets(x.post).map((k) => h("span", { class: "net", title: NET_NAME[k] }, NET_SHORT[k]))))));
    main.append(h("div", { class: "card" }, head, h("div", { class: "sec" },
      sp ? h("p", { class: "muted", style: "margin:0 0 8px" }, `Data especial: o conteúdo do dia prefere o tema “${sp.name}”. ${sp.hook}`) : null,
      list,
      yt > cap ? h("p", { class: "warn-t small" }, `⚠ ${yt} vídeos para o YouTube e o limite é ${cap}/dia: os últimos são pulados.`) : null)));
  }
  main.append(h("p", { class: "muted" }, "Os posts de cada dia são gerados às 05:20. As siglas mostram onde cada horário sai automaticamente; Kwai e o canal do WhatsApp são manuais."));
}

// ---------- histórico (por mês, filtrado no servidor)
const HIST = { month: "", type: "", net: "", errors: false };

async function renderHistory(main) {
  const q = new URLSearchParams({ ...(HIST.month && { month: HIST.month }), ...(HIST.type && { type: HIST.type }),
    ...(HIST.net && { net: HIST.net }), ...(HIST.errors && { errors: "1" }) });
  const box = h("div", {}, h("p", { class: "muted" }, "Carregando…"));
  main.append(box);
  let data;
  try { data = await api(`/api/history?${q}`); } catch (e) { box.replaceChildren(h("div", { class: "alert bad" }, e.message)); return; }
  if (TAB !== "historico") return;
  const month = data.month || dayOf().slice(0, 7);
  HIST.month = month;
  const months = data.months.some((m) => m.month === dayOf().slice(0, 7)) ? data.months : [{ month: dayOf().slice(0, 7), posts: 0 }, ...data.months];
  const reload = () => { const m = document.getElementById("main"); m.replaceChildren(); renderHistory(m); };
  const sel = (value, opts, on) => {
    const el = h("select", {}, opts.map(([v, n]) => h("option", { value: v, selected: v === value }, n)));
    el.addEventListener("change", () => on(el.value));
    return el;
  };
  const monthName = (m) => new Date(`${m}-15T12:00:00`).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  const errBox = h("input", { type: "checkbox", checked: HIST.errors });
  errBox.addEventListener("change", () => { HIST.errors = errBox.checked; reload(); });
  const filters = h("div", { class: "filters" },
    h("label", {}, "Mês", sel(month, months.map((m) => [m.month, `${monthName(m.month)} (${m.posts})`]), (v) => { HIST.month = v; reload(); })),
    h("label", {}, "Tipo", sel(HIST.type, [["", "Todos"], ...Object.entries(TYPE_NAME), ["compilation", LONG_NAME]], (v) => { HIST.type = v; reload(); })),
    h("label", {}, "Rede", sel(HIST.net, [["", "Todas"], ...NETS], (v) => { HIST.net = v; reload(); })),
    h("label", { class: "check" }, errBox, "Só com erro"));
  // a fila ainda tem posts deste mês: entram também, com os mesmos filtros
  const fromQueue = STATE.posts.filter((p) => p.date.startsWith(month) && (!HIST.type || p.type === HIST.type)
    && (!HIST.net || p.published?.[HIST.net] || p.publish_errors?.[HIST.net] || p.publish_skipped?.[HIST.net])
    && (!HIST.errors || Object.keys(p.publish_errors || {}).length));
  const ids = new Set(fromQueue.map((p) => p.id));
  const all = [...fromQueue, ...data.posts.filter((p) => !ids.has(p.id))]
    .filter((p) => Object.values(p.published || {}).some(Boolean) || Object.keys(p.publish_errors || {}).length)
    .sort((a, b) => dueAt(b).localeCompare(dueAt(a)));
  const table = h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Data"), h("th", {}, "Post"),
    ...NETS.map(([k]) => h("th", {}, NET_SHORT[k])))));
  const tbody = h("tbody");
  table.append(tbody);
  if (!all.length) tbody.append(h("tr", {}, h("td", { colspan: NETS.length + 2, class: "muted" }, "Nada neste mês com esses filtros.")));
  for (const p of all) {
    tbody.append(h("tr", {}, h("td", { class: "p" }, `${ddmm(p.date)} ${p.time || ""}`),
      h("td", {}, h("div", {}, titleOf(p)), h("div", { class: "muted" }, typeName(p.type))),
      ...NETS.map(([k]) => {
        const link = p.publish_links?.[k];
        if (p.published?.[k]) {
          return h("td", { title: p.published[k] }, link?.startsWith?.("http") ? h("a", { href: link, target: "_blank", rel: "noopener", title: "ver post" }, "✅↗") : "✅");
        }
        if (p.publish_errors?.[k]) return h("td", { title: p.publish_errors[k].message }, "❌");
        if (p.publish_skipped?.[k]) return h("td", { title: p.publish_skipped[k] }, "⏭");
        return h("td", {}, "—");
      })));
  }
  const counts = NETS.map(([k, n]) => `${n}: ${all.filter((p) => p.published?.[k]).length}`).join(" · ");
  box.replaceChildren(h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, "Publicações por rede"), filters,
    h("div", { style: "overflow-x:auto" }, table))),
    h("p", { class: "muted" }, `${monthName(month)}: ${all.length} post(s) — ${counts}`));
}

// ---------- métricas (mesma conta do resumo semanal, app/report.py)
// Indicador principal: TEMPO ASSISTIDO = visualizações × tempo médio, somando as redes.
// No YouTube sem tempo médio, usa o tempo médio do mesmo vídeo no Facebook (estimativa).
const num = (v) => (typeof v === "number" ? v : 0);
const MET_NETS = ["facebook", "instagram", "youtube"];
const VIDEO_CHANGE = "2026-10-17"; // mudança dos vídeos (comparação antes × depois); metrics.compare_from muda
let MET_NET = "all";

const netsOf = (net) => (net === "all" ? MET_NETS : [net]);
function watchOf(r, net = MET_NET) {
  const fbAvg = r.facebook?.avg_watch_s;
  let total = 0, seen = false;
  for (const n of netsOf(net)) {
    const d = r[n] || {};
    if (typeof d.views !== "number") continue;
    seen = true;
    if (typeof d.watch_time_s === "number" && d.watch_time_s > 0) total += d.watch_time_s;
    else if (typeof d.avg_watch_s === "number") total += d.views * d.avg_watch_s;
    else if (typeof fbAvg === "number") total += d.views * fbAvg;
  }
  return seen ? Math.round(total * 10) / 10 : null;
}
const viewsOf = (r, net = MET_NET) => netsOf(net).reduce((a, n) => a + num(r[n]?.views), 0);
const likesOf = (r, net = MET_NET) => netsOf(net).reduce((a, n) => a + num(r[n]?.likes), 0);
const commentsOf = (r, net = MET_NET) => netsOf(net).reduce((a, n) => a + num(r[n]?.comments), 0);
const hasNet = (r, net = MET_NET) => net === "all" || !!r[net];

function fmtTime(s) {
  if (s == null || s === "—") return "—";
  if (s >= 3600) return `${(s / 3600).toFixed(1).replace(".", ",")} h`;
  return s >= 120 ? `${(s / 60).toFixed(1).replace(".", ",")} min` : `${Math.round(s)} s`;
}
function avg(list, f) {
  const vals = list.map(f).filter((v) => typeof v === "number");
  return vals.length ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10 : "—";
}
const avgWatch = (list) => avg(list, (r) => watchOf(r));
const sortVal = (v) => (typeof v === "number" ? v : -1);
const br = (v) => (typeof v === "number" ? String(v).replace(".", ",") : v);

function groupTable(title, rows, keyFn, label) {
  const groups = {};
  for (const r of rows) (groups[keyFn(r)] ||= []).push(r);
  const ig = MET_NET === "instagram" && rows.some((r) => typeof r.instagram?.reach === "number");
  const head = ["", "Posts", "Tempo assistido/post", "Views/post", MET_NET === "all" ? "Tempo médio FB" : "Tempo médio",
    ig && "Alcance/post", "Curtidas/post", "Coment./post"].filter(Boolean);
  const avgNet = MET_NET === "all" ? "facebook" : MET_NET;
  const body = Object.entries(groups).sort((a, b) => sortVal(avgWatch(b[1])) - sortVal(avgWatch(a[1]))).map(([k, list]) =>
    h("tr", {}, h("td", {}, label(k)), h("td", {}, list.length), h("td", {}, h("b", {}, fmtTime(avgWatch(list)))),
      h("td", {}, br(avg(list, (r) => viewsOf(r)))),
      h("td", {}, secs(avg(list, (r) => r[avgNet]?.avg_watch_s))),
      ig && h("td", {}, br(avg(list, (r) => r.instagram?.reach))),
      h("td", {}, br(avg(list, (r) => likesOf(r)))), h("td", {}, br(avg(list, (r) => commentsOf(r))))));
  return h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, title),
    h("div", { style: "overflow-x:auto" }, h("table", {}, h("thead", {}, h("tr", {}, head.map((t) => h("th", {}, t)))), h("tbody", {}, body)))));
}

// antes × depois da mudança dos vídeos, por formato (fora o vídeo longo e o repost, como no resumo)
function compareTable(rows) {
  const cut = STATE.settings?.metrics?.compare_from || VIDEO_CHANGE;
  const fair = rows.filter((r) => r.type && r.type !== "compilation" && !r.repost_of && r.date);
  const before = fair.filter((r) => r.date < cut), after = fair.filter((r) => r.date >= cut);
  if (!before.length || !after.length) {
    return h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, `Antes × depois de ${ddmm(cut)}`),
      h("p", { class: "muted" }, after.length ? `Ainda sem posts de antes de ${ddmm(cut)} nas métricas (só 60 dias são coletados).`
        : `Ainda sem posts a partir de ${ddmm(cut)} com métricas. A comparação aparece nos próximos dias.`)));
  }
  const types = [...new Set(fair.map((r) => r.type))];
  const pct = (a, b) => (typeof a === "number" && typeof b === "number" && a > 0 ? Math.round(((b - a) / a) * 100) : null);
  const delta = (p) => (p == null ? "—" : h("b", { class: p >= 0 ? "ok-t" : "bad-t" }, `${p > 0 ? "+" : ""}${p}%`));
  const line = (label, b, a) => {
    const wb = avgWatch(b), wa = avgWatch(a), vb = avg(b, (r) => viewsOf(r)), va = avg(a, (r) => viewsOf(r));
    return h("tr", {}, h("td", {}, label), h("td", {}, `${b.length} → ${a.length}`),
      h("td", { class: "p" }, `${fmtTime(wb)} → `, h("b", {}, fmtTime(wa))), h("td", {}, delta(pct(wb, wa))),
      h("td", { class: "p" }, `${br(vb)} → `, h("b", {}, br(va))), h("td", {}, delta(pct(vb, va))));
  };
  const body = types.map((t) => [t, before.filter((r) => r.type === t), after.filter((r) => r.type === t)])
    .filter(([, b, a]) => b.length && a.length)
    .sort((x, y) => sortVal(avgWatch(y[2])) - sortVal(avgWatch(x[2])))
    .map(([t, b, a]) => line(typeName(t), b, a));
  body.push(line(h("b", {}, "Todos"), before, after));
  return h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, `Antes × depois de ${ddmm(cut)} (mudança dos vídeos)`),
    h("p", { class: "muted" }, "Média por post. Formatos que só aparecem de um lado ficam de fora."),
    h("div", { style: "overflow-x:auto" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Formato", "Posts", "Tempo assistido/post", "Variação", "Views/post", "Variação"].map((x) => h("th", {}, x)))),
      h("tbody", {}, body)))));
}

const secs = (v) => (typeof v === "number" ? `${String(v).replace(".", ",")} s` : "—");
// quais vídeos prendem a atenção: tempo médio assistido no Facebook (precisa de read_insights)
function retentionTable(rows) {
  const vids = rows.filter((r) => typeof r.facebook?.avg_watch_s === "number")
    .sort((a, b) => b.facebook.avg_watch_s - a.facebook.avg_watch_s);
  if (!vids.length) return null;
  const pct = (r) => (r.facebook.views ? `${Math.round((num(r.facebook.complete_views) / r.facebook.views) * 100)}%` : "—");
  const line = (r) => h("tr", {},
    h("td", {}, h("b", {}, secs(r.facebook.avg_watch_s))),
    h("td", {}, h("div", {}, r.title), h("div", { class: "muted" }, `${typeName(r.type)} · ${r.date?.split("-").reverse().join("/")} ${r.time || ""}`)),
    h("td", {}, r.facebook.views ?? "—"), h("td", {}, r.facebook.views_3s ?? "—"), h("td", {}, pct(r)),
    h("td", { class: "p" }, r.links?.facebook ? h("a", { href: r.links.facebook, target: "_blank", rel: "noopener" }, "FB↗") : ""));
  const shown = vids.length > 10 ? [...vids.slice(0, 5), ...vids.slice(-5)] : vids;
  return h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, "Vídeos que prendem a atenção (Facebook)"),
    h("p", { class: "muted" }, vids.length > 10 ? "Os 5 com maior e os 5 com menor tempo médio assistido." : "Ordenados pelo tempo médio assistido."),
    h("div", { style: "overflow-x:auto" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Tempo médio", "Vídeo", "Views", "Views 3 s", "Até o fim", ""].map((t) => h("th", {}, t)))),
      h("tbody", {}, shown.map(line))))));
}

// gráficos simples em HTML/CSS (sem biblioteca): colunas por dia e barras por horário
function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].map((m) => m * p).find((m) => m >= v);
}
function chartTip(box) {
  const tip = h("div", { class: "ch-tip", role: "status" });
  box.append(tip);
  return {
    show(el, html) {
      tip.replaceChildren(...html);
      tip.classList.add("on");
      const b = box.getBoundingClientRect(), r = el.getBoundingClientRect();
      const x = Math.min(Math.max(r.left + r.width / 2 - b.left, 70), b.width - 70);
      tip.style.left = `${x}px`;
      tip.style.top = `${Math.max(r.top - b.top - 8, 0)}px`;
    },
    hide() { tip.classList.remove("on"); },
  };
}
// tempo assistido total por dia, em minutos
function dailyChart(rows) {
  const byDay = {};
  for (const r of rows) {
    if (!r.date) continue;
    const d = (byDay[r.date] ||= { w: 0, posts: 0 });
    d.w += (watchOf(r) || 0) / 60; d.posts += 1;
  }
  const days = Object.keys(byDay).sort().slice(-30);
  if (!days.length) return null;
  for (const d of days) byDay[d].w = Math.round(byDay[d].w * 10) / 10;
  const max = niceMax(Math.max(...days.map((d) => byDay[d].w)));
  const peak = days.reduce((a, d) => (byDay[d].w > byDay[a].w ? d : a), days[0]);
  const plot = h("div", { class: "ch-plot" });
  const box = h("div", { class: "ch-box cols" },
    h("div", { class: "ch-grid" }, [1, 0.5, 0].map((f) =>
      h("div", { class: "ch-line", style: `bottom:${f * 100}%` }, h("span", {}, Math.round(max * f))))),
    plot);
  const tip = chartTip(box);
  for (const d of days) {
    const { w, posts } = byDay[d];
    const col = h("div", { class: "ch-col", tabindex: "0", "aria-label": `${ddmm(d)}: ${br(w)} min assistidos, ${posts} posts` },
      h("div", { class: "ch-bar", style: `height:${(w / max) * 100}%` },
        d === peak && w > 0 ? h("span", { class: "ch-val" }, br(w)) : null));
    const show = () => tip.show(col, [h("b", {}, ddmm(d)), h("div", {}, `Assistido: ${fmtTime(w * 60)}`), h("div", { class: "muted" }, `${posts} post(s)`)]);
    col.addEventListener("pointerenter", show);
    col.addEventListener("focus", show);
    col.addEventListener("pointerleave", tip.hide);
    col.addEventListener("blur", tip.hide);
    plot.append(col);
  }
  const mid = days[Math.floor(days.length / 2)];
  const axis = h("div", { class: "ch-axis" }, h("span", {}, ddmm(days[0])),
    days.length > 2 ? h("span", {}, ddmm(mid)) : null, days.length > 1 ? h("span", {}, ddmm(days.at(-1))) : null);
  return h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, "Tempo assistido por dia (minutos)"), box, axis));
}
function hourChart(rows) {
  const groups = {};
  for (const r of rows) if (r.time && watchOf(r) != null) (groups[r.time] ||= []).push(r);
  const items = Object.keys(groups).sort().map((t) => ({ t, v: avgWatch(groups[t]), n: groups[t].length }));
  if (!items.length) return null;
  const max = niceMax(Math.max(...items.map((i) => (typeof i.v === "number" ? i.v : 0))));
  const list = h("div", { class: "ch-hbars" });
  const box = h("div", { class: "ch-box" }, list);
  const tip = chartTip(box);
  for (const { t, v, n } of items) {
    const val = typeof v === "number" ? v : 0;
    const track = h("div", { class: "ch-track" }, h("div", { class: "ch-hbar", style: `width:${(val / max) * 100}%` }));
    const row = h("div", { class: "ch-hrow", tabindex: "0", "aria-label": `${t}: ${fmtTime(val)} assistidos por post, ${n} posts` },
      h("span", { class: "ch-hlab" }, t), track, h("span", { class: "ch-hval" }, fmtTime(val)));
    const show = () => tip.show(track, [h("b", {}, t), h("div", {}, `Tempo assistido/post: ${fmtTime(val)}`), h("div", { class: "muted" }, `${n} post(s)`)]);
    row.addEventListener("pointerenter", show);
    row.addEventListener("focus", show);
    row.addEventListener("pointerleave", tip.hide);
    row.addEventListener("blur", tip.hide);
    list.append(row);
  }
  return h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, "Tempo assistido por post, por horário"), box));
}

function downloadCsv(rows) {
  const cols = ["id", "date", "time", "type", "title", "hook", "repost_of"];
  const fields = { facebook: ["views", "avg_watch_s", "watch_time_s", "likes", "comments", "shares"],
    instagram: ["views", "reach", "likes", "comments", "saved", "shares"], youtube: ["views", "avg_watch_s", "likes", "comments"] };
  const head = [...cols, "tempo_assistido_s", "views_total", ...Object.entries(fields).flatMap(([n, fs]) => fs.map((f) => `${n}_${f}`))];
  // Excel em português: separador ";" e vírgula decimal
  const cell = (v) => {
    if (v == null) return "";
    const s = typeof v === "number" ? String(v).replace(".", ",") : String(v);
    return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [head.join(";"), ...rows.map((r) => [...cols.map((c) => r[c]), watchOf(r, "all"), viewsOf(r, "all"),
    ...Object.entries(fields).flatMap(([n, fs]) => fs.map((f) => r[n]?.[f]))].map(cell).join(";"))];
  const url = URL.createObjectURL(new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" }));
  const a = h("a", { href: url, download: `metricas-${dayOf()}.csv` });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

let METRICS = null;
async function renderMetrics(main) {
  const refresh = h("button", { class: "btn small", onclick: async () => {
    try { await api("/api/metrics", { method: "POST", body: {} }); toast("Atualizando métricas… (~1 min). A tela atualiza sozinha."); METRICS = null; kickPoll(); }
    catch (e) { toast(e.message); }
  } }, "↻ Atualizar métricas");
  const csv = h("button", { class: "btn small", onclick: () => downloadCsv(Object.entries(METRICS?.posts || {}).map(([id, r]) => ({ id, ...r }))) }, "⬇ Baixar CSV");
  main.append(h("div", { class: "row", style: "margin-bottom:12px" }, refresh, csv));
  let data;
  try { data = METRICS = await api("/api/metrics"); } catch (e) { main.append(h("div", { class: "alert bad" }, e.message)); return; }
  if (TAB !== "metricas") return;
  const all = Object.entries(data.posts || {}).map(([id, r]) => ({ id, ...r }));
  if (!all.length) {
    main.append(h("div", { class: "empty" }, "Ainda sem métricas. Elas são coletadas a cada publicação (ou toque em Atualizar)."));
    return;
  }
  const tabs = h("div", { class: "tabs", style: "margin-bottom:12px" },
    [["all", "Todas as redes"], ["facebook", "Facebook"], ["youtube", "YouTube"], ["instagram", "Instagram"]].map(([k, n]) =>
      h("button", { class: MET_NET === k ? "on" : "", onclick: () => { MET_NET = k; render(); } }, n)));
  main.append(tabs);
  const rows = all.filter((r) => hasNet(r));
  const when = data.updated_at ? new Date(data.updated_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "";
  const total = rows.reduce((a, r) => a + (watchOf(r) || 0), 0);
  main.append(h("p", { class: "muted" }, `${rows.length} posts dos últimos 60 dias · ${fmtTime(total)} assistidos · ${rows.reduce((a, r) => a + viewsOf(r), 0)} views · atualizado em ${when}. `,
    "Indicador: tempo assistido (views × tempo médio), a mesma conta do resumo semanal. No YouTube sem tempo médio, usa o do Facebook."));
  for (const n of data.notes || []) main.append(h("div", { class: "alert warn" }, n));
  if (!rows.length) { main.append(h("div", { class: "empty" }, "Nenhum post com números desta rede ainda.")); return; }
  main.append(dailyChart(rows) || "", hourChart(rows) || "", compareTable(rows));
  const top = rows.filter((r) => watchOf(r) != null).sort((a, b) => watchOf(b) - watchOf(a) || viewsOf(b) - viewsOf(a)).slice(0, 10);
  main.append(h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, "Top 10 por tempo assistido"),
    top.length ? h("table", {}, h("tbody", {}, top.map((r) => h("tr", {},
      h("td", { class: "p" }, h("b", {}, fmtTime(watchOf(r))), h("div", { class: "muted" }, `${viewsOf(r)} views`)),
      h("td", {}, h("div", {}, r.title), h("div", { class: "muted" }, `${typeName(r.type)} · ${r.date?.split("-").reverse().join("/")} ${r.time}`)),
      h("td", { class: "p" }, Object.entries(r.links || {}).map(([k, u]) => h("a", { href: u, target: "_blank", rel: "noopener", style: "margin-right:6px" }, NET_SHORT[k] || k.slice(0, 2).toUpperCase())))))))
      : h("p", { class: "muted" }, "Sem vídeos com visualizações ainda."))));
  if (MET_NET === "all" || MET_NET === "facebook") main.append(retentionTable(rows) || "");
  main.append(groupTable("Por tipo de post", rows, (r) => r.type, (k) => typeName(k)));
  main.append(groupTable("Por horário", rows.filter((r) => r.time), (r) => r.time, (k) => k));
}

// ---------- configurações
function renderConfig(main) {
  const s = STATE.settings || {};
  const slots = s.schedule?.slots || [];
  const f = h("form", { class: "stack" });
  const name = h("input", { type: "text", value: s.brand?.name || "" });
  const handle = h("input", { type: "text", value: s.brand?.handle || "", placeholder: "@seuperfil" });
  const channel = h("input", { type: "url", value: s.brand?.whatsapp_channel || "", placeholder: "https://whatsapp.com/channel/..." });
  const slotBox = h("div", { class: "stack" });
  const slotRows = [];
  const addSlot = (slot) => {
    if (slotRows.length >= 12) return toast("Máximo de 12 posts por dia");
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
  const pubBoxes = Object.fromEntries(["instagram", "facebook", "youtube", "stories", "tiktok"].map((k) =>
    [k, h("input", { type: "checkbox", checked: !!s.publishing?.[k] })]));
  const comp = s.compilation || {};
  const compOn = h("input", { type: "checkbox", checked: comp.enabled !== false && !!s.compilation });
  const compDay = h("select", {}, WEEKDAYS.map((n, i) => h("option", { value: i, selected: i === (comp.weekday ?? 6) }, n)));
  const compTime = h("input", { type: "time", value: comp.time || "18:00" });
  const compMin = h("input", { type: "number", min: 3, max: 20, value: comp.minutes ?? 10 });
  const compNow = h("button", { type: "button", class: "btn small", onclick: async () => {
    if (!confirm("Gerar agora um vídeo longo de quiz?\n\nLeva uns 12 a 20 minutos. Ele aparece na Fila quando ficar pronto.")) return;
    compNow.disabled = true;
    try { await api("/api/generate", { method: "POST", body: { compilation: true } }); GEN_UNTIL = Date.now() + 3 * 60e3; kickPoll(); toast("Gerando o vídeo longo! Leva uns 12 a 20 minutos. A tela atualiza sozinha."); }
    catch (err) { toast(err.message); }
    compNow.disabled = false;
  } }, "Gerar vídeo longo agora");
  const vt = s.video?.video_types || ["quiz"];
  const vidVerse = h("input", { type: "checkbox", checked: vt.includes("verse") });
  const vidCur = h("input", { type: "checkbox", checked: vt.includes("curiosity") });
  const groqOn = h("input", { type: "checkbox", checked: s.groq?.enabled !== false });
  const model = h("input", { type: "text", value: s.groq?.model || "" });
  const calls = h("input", { type: "number", min: 0, max: 50, value: s.groq?.max_calls_per_day ?? 6 });
  const ratio = h("input", { type: "number", min: 0, max: 1, step: 0.1, value: s.groq?.new_content_ratio ?? 0.3 });
  f.append(
    h("label", {}, "Nome da página", name),
    h("label", {}, "Seu @ (marca d'água nos vídeos e imagens)", handle),
    h("label", {}, "Link do canal do WhatsApp (aparece no site /hoje/; vazio = sem botão)", channel),
    h("h3", {}, "Posts por dia (horários sugeridos para postar)"),
    slotBox,
    h("button", { type: "button", class: "btn small", onclick: () => addSlot() }, "+ Adicionar horário"),
    h("p", { class: "muted" }, "Os posts do dia são gerados de madrugada (05:20). Com a publicação automática ligada, cada post aprovado sai no horário dele (até ~7 min depois). Use horários cheios (ex.: 12:00)."),
    h("label", { class: "check" }, auto, "Aprovar automaticamente (sem revisão)"),
    h("h3", {}, "Publicação automática (ao aprovar, no horário do post)"),
    h("label", { class: "check" }, pubBoxes.instagram, "Instagram (versículo no feed, quiz no Reels)"),
    h("label", { class: "check" }, pubBoxes.facebook, "Facebook (Página)"),
    h("label", { class: "check" }, pubBoxes.stories, "Stories do Instagram (imagem 9:16 ou o vídeo do quiz)"),
    h("label", { class: "check" }, pubBoxes.youtube, "YouTube Shorts (quiz; fica privado até a auditoria do YouTube)"),
    h("label", { class: "check" }, pubBoxes.tiktok, "TikTok (Reels vão para os rascunhos do app: você escolhe a música e publica)"),
    h("div", { class: "row" },
      STATE.tiktok?.connected
        ? h("span", { class: "muted" }, `TikTok conectado${STATE.tiktok.name ? `: ${STATE.tiktok.name}` : ""} ✔`)
        : h("span", { class: "muted" }, "TikTok não conectado."),
      h("a", { class: "btn small", href: "/api/tiktok/connect" }, STATE.tiktok?.connected ? "Reconectar TikTok" : "Conectar TikTok")),
    h("p", { class: "muted" }, "Kwai e o canal do WhatsApp continuam manuais (no canal, use o botão 📲 da legenda). Cada rede precisa das chaves configuradas (veja docs/PUBLICACAO.md e docs/TIKTOK.md)."),
    h("h3", {}, "Vídeo longo de quiz (YouTube)"),
    h("label", { class: "check" }, compOn, "Gerar toda semana um vídeo de ~10 min com várias perguntas (sai só no YouTube)"),
    h("div", { class: "row" }, h("label", {}, "Dia", compDay), h("label", {}, "Horário", compTime), h("label", {}, "Minutos", compMin)),
    h("div", { class: "row" }, compNow),
    h("p", { class: "muted" }, "Usa os quizzes dos últimos dias e completa com perguntas novas do banco. A geração leva uns 12 a 20 minutos."),
    h("h3", {}, "Vídeos (Reels e Shorts)"),
    h("p", { class: "muted" }, "O quiz sempre sai em vídeo. Marque para o Versículo e o “Você sabia?” também virarem vídeo (em vez de só imagem). Cada vídeo no YouTube gasta 1.600 dos 10.000 pontos diários grátis: com 6 vídeos por dia mais o vídeo longo de sábado, passa do limite."),
    h("label", { class: "check" }, vidCur, "“Você sabia?” também em vídeo"),
    h("label", { class: "check" }, vidVerse, "Versículo do dia também em vídeo"),
    h("h3", {}, "Inteligência artificial (Groq)"),
    h("label", { class: "check" }, groqOn, "Usar a Groq para conteúdo novo e variações de legenda"),
    h("label", {}, "Modelo", model),
    h("label", {}, "Máximo de chamadas por dia", calls),
    h("label", {}, "Chance de conteúdo novo pela IA (0 a 1)", ratio),
    h("p", { class: "muted" }, `Uso hoje: ${STATE.groq?.date === dayOf() ? STATE.groq.calls : 0} chamada(s).`),
  );
  const save = h("button", { class: "btn primary" }, "Salvar configurações");
  f.append(save);
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    save.disabled = true;
    try {
      const r = await api("/api/settings", { method: "PUT", body: {
        name: name.value, handle: handle.value, whatsapp_channel: channel.value,
        slots: slotRows.map((r) => ({ time: r.time.value, type: r.type.value }))
          .sort((a, b) => a.time.localeCompare(b.time)),
        auto_approve: auto.checked, groq_enabled: groqOn.checked, model: model.value.trim(),
        publishing: Object.fromEntries(Object.entries(pubBoxes).map(([k, b]) => [k, b.checked])),
        max_calls_per_day: Number(calls.value), new_content_ratio: Number(ratio.value),
        video_types: ["quiz", ...(vidCur.checked ? ["curiosity"] : []), ...(vidVerse.checked ? ["verse"] : [])],
        compilation: { enabled: compOn.checked, weekday: Number(compDay.value), time: compTime.value, minutes: Number(compMin.value) },
      } });
      STATE.settings = r.settings;
      toast("Configurações salvas! Valem a partir da próxima geração.");
    } catch (err) { toast(err.message); }
    save.disabled = false;
  });
  main.append(generateCard(), h("div", { class: "card" }, h("div", { class: "sec" }, f)));
}

// Gerar fora do horário: "só o que falta" não apaga nada; "do zero" apaga a fila (pede confirmação digitada).
function generateCard() {
  const n = STATE.settings?.schedule?.slots?.length || 0;
  const run = async (btn, clear) => {
    btn.disabled = true;
    try {
      await api("/api/generate", { method: "POST", body: { clear } });
      GEN_UNTIL = Date.now() + 3 * 60e3;
      toast(clear ? "Refazendo o dia do zero (~4–6 min). A tela atualiza sozinha." : "Gerando o que falta (~4–6 min). A tela atualiza sozinha.");
      kickPoll();
    } catch (err) { toast(err.message); }
    btn.disabled = false;
  };
  const missing = h("button", { type: "button", class: "btn primary", onclick: () => {
    if (confirm("Gerar só os posts de hoje que estão faltando?\n\nNada é apagado: os posts que já existem ficam como estão; os rejeitados e ainda não publicados são refeitos.")) run(missing, false);
  } }, "Gerar só o que falta");
  const redo = h("button", { type: "button", class: "btn bad", onclick: () => {
    const typed = prompt(`Refazer o dia do zero APAGA os posts atuais da fila e gera ${n} novos para hoje.\n\nOs já publicados continuam no Histórico. Posts cujo horário já passou ficam aguardando você (use “Publicar agora”).\n\nPara confirmar, digite REFAZER:`, "");
    if (typed === null) return;
    if (typed.trim().toUpperCase() !== "REFAZER") return toast("Nada feito: digite REFAZER para confirmar.");
    run(redo, true);
  } }, "Refazer o dia do zero");
  return h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, "Gerar posts de hoje agora"),
    h("p", { class: "muted", style: "margin-top:0" }, "A geração automática roda às 05:20. Use aqui se ela falhou ou se você rejeitou posts."),
    h("div", { class: "row" }, missing, redo)));
}

// ---------- geral
// faixas no topo: publicações pausadas e GitHub Actions rodando
function missedDuringPause() {
  const now = nowLocal();
  return STATE.posts.filter((p) => p.status === "approved" && p.media?.base && dueAt(p) <= now && pendingNets(p).length).length;
}

async function setPaused(value, skipMissed = false) {
  try {
    let reason = "";
    if (value) {
      reason = prompt("Pausar TODAS as publicações automáticas (Instagram, Facebook, YouTube, Stories, TikTok)?\n\nNada sai até você retomar. Motivo (opcional, ex.: luto, viagem):", "");
      if (reason === null) return;
    }
    const r = await api("/api/pause", { method: "POST", body: { paused: value, skip_missed: skipMissed, reason } });
    STATE.settings = r.settings;
    if (r.skipped) STATE = { ...STATE, ...(await api("/api/state")) };
    toast(value ? "⏸ Publicações pausadas." : r.skipped ? `▶ Publicações retomadas. ${r.skipped} post(s) atrasado(s) pulados.` : "▶ Publicações retomadas.");
    render();
    if (!value) kickPoll();
  } catch (e) { toast(e.message); }
}

function renderBanners() {
  const box = document.getElementById("banners");
  box.replaceChildren();
  const pauseBtn = document.getElementById("pause");
  pauseBtn.textContent = paused() ? "▶ Retomar" : "⏸ Pausar publicações";
  pauseBtn.classList.toggle("bad", !paused());
  if (paused()) {
    const pub = STATE.settings.publishing;
    const missed = missedDuringPause();
    box.append(h("div", { class: "banner bad" },
      h("div", {}, h("b", {}, "⏸ Publicações pausadas"),
        pub.paused_at ? ` desde ${new Date(pub.paused_at).toLocaleString("pt-BR", { timeZone: TZ(), dateStyle: "short", timeStyle: "short" })}` : "",
        pub.paused_reason ? ` · ${pub.paused_reason}` : "", ". Nada é publicado nas redes até você retomar."),
      h("div", { class: "row" },
        h("button", { class: "btn small", onclick: () => setPaused(false, true) }, missed ? `Retomar e pular ${missed} atrasado(s)` : "Retomar"),
        missed ? h("button", { class: "btn small", onclick: () => {
          if (confirm(`Retomar e publicar agora os ${missed} post(s) cujo horário passou durante a pausa?`)) setPaused(false, false);
        } }, "Retomar e publicar os atrasados") : null)));
  }
  const gen = RUNS.pipeline && RUNS.pipeline.event !== "push";
  if (gen || GEN_UNTIL > Date.now()) {
    const rerender = STATE.posts.some((p) => p.needs_render);
    box.append(h("div", { class: "banner run" }, h("span", { class: "spin", "aria-hidden": "true" }),
      h("span", {}, rerender ? "Refazendo o vídeo editado… " : "Gerando… ", h("span", { class: "muted" }, "(GitHub Actions rodando, a tela atualiza sozinha)")),
      RUNS.pipeline?.url ? h("a", { href: RUNS.pipeline.url, target: "_blank", rel: "noopener" }, "ver ↗") : null));
  } else if (RUNS.publish) {
    box.append(h("div", { class: "banner run" }, h("span", { class: "spin", "aria-hidden": "true" }),
      h("span", {}, "Publicando nas redes… ", h("span", { class: "muted" }, "(GitHub Actions rodando)")),
      h("a", { href: RUNS.publish.url, target: "_blank", rel: "noopener" }, "ver ↗")));
  }
}

function render() {
  EDITING = false;
  const main = document.getElementById("main");
  main.replaceChildren();
  document.getElementById("brand").textContent = STATE.settings?.brand?.name || "Painel";
  renderBanners();
  if (TAB === "hoje") renderToday(main);
  else if (TAB === "fila") renderQueue(main);
  else if (TAB === "agenda") renderAgenda(main);
  else if (TAB === "historico") renderHistory(main);
  else if (TAB === "metricas") renderMetrics(main);
  else renderConfig(main);
}

// ---------- atualização automática
// Enquanto algo está rodando (geração, vídeo refeito, publicação), consulta /api/state a cada 40 s
// e redesenha a tela; para sozinha quando termina.
let GEN_UNTIL = 0; // acabou de pedir uma geração: espera o GitHub Actions aparecer
let POLL_TIMER = null;

function busy() {
  const recent = (t) => t && Date.now() - Date.parse(t) < 10 * 60e3;
  return !!(RUNS.pipeline || RUNS.publish || GEN_UNTIL > Date.now()
    || STATE.posts.some((p) => p.needs_render || recent(p.publishing_now)));
}

async function fetchRuns() {
  try { RUNS = await api("/api/runs"); } catch { RUNS = { pipeline: null, publish: null }; }
}

async function pollTick() {
  POLL_TIMER = null;
  if (document.hidden) return; // volta ao abrir a aba (visibilitychange)
  const wasGenerating = !!RUNS.pipeline && RUNS.pipeline.event !== "push";
  const wasPublishing = !!RUNS.publish;
  const before = JSON.stringify([STATE.posts, STATE.settings, STATE.health, STATE.groq]);
  try {
    const [st] = await Promise.all([api("/api/state"), fetchRuns()]);
    STATE = st;
  } catch { /* rede instável: tenta na próxima */ }
  const changed = before !== JSON.stringify([STATE.posts, STATE.settings, STATE.health, STATE.groq]);
  const playing = [...document.querySelectorAll("video")].some((v) => !v.paused);
  if (changed && !EDITING && !playing && ["hoje", "fila", "agenda"].includes(TAB)) render();
  else renderBanners();
  if (wasGenerating && !RUNS.pipeline && GEN_UNTIL < Date.now()) toast("✅ Terminou: a fila está atualizada.");
  if (wasPublishing && !RUNS.publish && TAB === "metricas") render(); // a coleta de métricas roda junto
  schedulePoll();
}

function schedulePoll() {
  if (!POLL_TIMER && busy()) POLL_TIMER = setTimeout(pollTick, POLL_MS);
}

function kickPoll() {
  renderBanners();
  schedulePoll();
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && busy() && !POLL_TIMER) POLL_TIMER = setTimeout(pollTick, 500);
});

async function load() {
  try {
    const [st] = await Promise.all([api("/api/state"), fetchRuns()]);
    STATE = st;
    render();
    schedulePoll();
  } catch (e) {
    if (e.message !== "login") document.getElementById("main").replaceChildren(h("div", { class: "alert bad" }, e.message));
  }
}

document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => {
  TAB = b.dataset.tab;
  document.querySelectorAll("nav button").forEach((x) => x.classList.toggle("on", x === b));
  render();
}));
document.getElementById("pause").addEventListener("click", () => {
  if (!paused()) return setPaused(true);
  const missed = missedDuringPause();
  if (confirm(missed ? `Retomar as publicações?\n\n${missed} post(s) tiveram o horário durante a pausa e serão PULADOS (não saem). Para publicá-los, use o botão “Retomar e publicar os atrasados” na faixa vermelha.` : "Retomar as publicações?")) setPaused(false, true);
});
document.getElementById("logout").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  location.href = "/login";
});
load();
