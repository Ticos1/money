"use strict";
// Painel: fila de posts, pré-visualização, download, legendas e histórico.

const PLATFORMS = [
  ["instagram", "Instagram"], ["facebook", "Facebook"], ["tiktok", "TikTok"],
  ["kwai", "Kwai"], ["youtube", "YouTube"], ["whatsapp", "Canal WhatsApp"],
];
// redes de publicação (as legendas usam PLATFORMS; Stories não tem legenda)
const NETS = [...PLATFORMS, ["stories", "Stories IG"]];
const TYPE_NAME = { verse: "Versículo do dia", quiz: "Desafio de quiz (Reels)", curiosity: "Você sabia?",
  fill: "Complete o versículo (Reels)", truefalse: "Verdadeiro ou falso (Reels)" };
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
  return `${day} · ${postTime(post)}`;
}

// horário real de saída (o do slot ± alguns minutos, para não parecer automação)
function postTime(post) {
  return post.publish_at?.slice(11, 16) || post.time;
}

function titleOf(post) {
  if (post.type === "compilation") return post.content.title;
  if (post.type === "fill") return `Complete: ${post.content.ref_label}`;
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
  } else if (post.type === "fill" || post.type === "truefalse") {
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
    const content = (post.type === "fill" || post.type === "truefalse") ? {} : post.type === "verse"
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
      toast(r.rerender ? "Salvo! O vídeo está sendo refeito (~3 min)." : "Legendas salvas!");
      render();
    } catch (err) { toast(err.message); save.disabled = false; }
  });
  card.replaceChildren(h("div", { class: "sec" }, h("h3", {}, `Editar · ${fmtDate(post)}`), f));
}

// Redes ligadas em Configurações onde este post ainda não saiu.
function pendingNets(post) {
  const on = Object.entries(STATE.settings?.publishing || {}).filter(([, v]) => v === true).map(([k]) => k)
    .filter((k) => post.type !== "compilation" || k === "youtube")
    .filter((k) => !Array.isArray(STATE.settings?.publishing?.[`${k}_types`])
      || STATE.settings.publishing[`${k}_types`].includes(post.type))
    .filter((k) => k !== "tiktok" || post.media?.video_silent);
  return on.filter((k) => !post.published?.[k] && !post.publish_skipped?.[k] && (k !== "youtube" || post.media?.video_music)
    && (k !== "stories" || post.media?.video_music || post.media?.images?.includes("imagem_story.jpg")));
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
      ? (auto.length ? `Aprovado! Será publicado em ${auto.join(", ")} no horário (${postTime(post)}).` : "Aprovado!")
      : action === "reject" ? "Rejeitado" : "Atualizado");
    render();
  } catch (e) { toast(e.message); }
}

function postCard(post) {
  const card = h("article", { class: "card" });
  const head = h("div", { class: "card-h" },
    h("span", { class: "when" }, fmtDate(post)),
    h("span", { class: "chip" }, typeName(post.type)),
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
    ...NETS.map(([k, n]) => h("th", {}, k === "whatsapp" ? "WA" : n.slice(0, 2))))));
  const tbody = h("tbody");
  table.append(tbody);
  main.append(h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, "Publicações por rede"),
    h("div", { style: "overflow-x:auto" }, table))));
  let older = [];
  try { older = (await api("/api/history")).posts; } catch (e) { toast(e.message); }
  const all = [...STATE.posts, ...older].filter((p) => Object.values(p.published || {}).some(Boolean));
  if (!all.length) tbody.append(h("tr", {}, h("td", { colspan: NETS.length + 2, class: "muted" }, "Nada publicado ainda. Marque as redes em cada post da fila.")));
  for (const p of all) {
    tbody.append(h("tr", {}, h("td", { class: "p" }, p.date.split("-").reverse().join("/")),
      h("td", {}, h("div", {}, titleOf(p)), h("div", { class: "muted" }, typeName(p.type))),
      ...NETS.map(([k]) => {
        const link = p.publish_links?.[k];
        const mark = p.published?.[k]
          ? (link?.startsWith?.("http") ? h("a", { href: link, target: "_blank", rel: "noopener", title: "ver post" }, "✅↗") : "✅")
          : "—";
        return h("td", { title: p.published?.[k] || "" }, mark);
      })));
  }
  const counts = NETS.map(([k, n]) => `${n}: ${all.filter((p) => p.published?.[k]).length}`).join(" · ");
  main.append(h("p", { class: "muted" }, `Total publicado — ${counts}`));
}

// ---------- métricas
const num = (v) => (typeof v === "number" ? v : 0);
function engagement(r) {
  const ig = r.instagram || {}, fb = r.facebook || {}, yt = r.youtube || {};
  return num(ig.likes) + num(ig.comments) * 2 + num(ig.saved) * 3 + num(ig.shares) * 3
    + num(fb.likes) + num(fb.comments) * 2 + num(fb.shares) * 3 + num(yt.likes) + num(yt.comments) * 2;
}
function avg(list, f) {
  const vals = list.map(f).filter((v) => typeof v === "number");
  return vals.length ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10 : "—";
}
function groupTable(title, rows, keyFn, label) {
  const groups = {};
  for (const r of rows) (groups[keyFn(r)] ||= []).push(r);
  const hasReach = rows.some((r) => typeof r.instagram?.reach === "number");
  const hasFbViews = rows.some((r) => typeof r.facebook?.views === "number");
  const head = ["", "Posts", "Engaj. médio", "Curtidas IG", hasReach && "Alcance IG", "Curtidas FB",
    hasFbViews && "Views FB", hasFbViews && "Tempo médio FB", "Views YT"].filter(Boolean);
  const body = Object.entries(groups).sort((a, b) => avg(b[1], engagement) - avg(a[1], engagement)).map(([k, list]) =>
    h("tr", {}, h("td", {}, label(k)), h("td", {}, list.length), h("td", {}, h("b", {}, avg(list, engagement))),
      h("td", {}, avg(list, (r) => r.instagram?.likes)), hasReach && h("td", {}, avg(list, (r) => r.instagram?.reach)),
      h("td", {}, avg(list, (r) => r.facebook?.likes)),
      hasFbViews && h("td", {}, avg(list, (r) => r.facebook?.views)),
      hasFbViews && h("td", {}, secs(avg(list, (r) => r.facebook?.avg_watch_s))),
      h("td", {}, avg(list, (r) => r.youtube?.views))));
  return h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, title),
    h("div", { style: "overflow-x:auto" }, h("table", {}, h("thead", {}, h("tr", {}, head.map((t) => h("th", {}, t)))), h("tbody", {}, body)))));
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
function dailyChart(rows) {
  const byDay = {};
  for (const r of rows) {
    if (!r.date) continue;
    const d = (byDay[r.date] ||= { eng: 0, posts: 0 });
    d.eng += engagement(r); d.posts += 1;
  }
  const days = Object.keys(byDay).sort().slice(-30);
  if (!days.length) return null;
  const max = niceMax(Math.max(...days.map((d) => byDay[d].eng)));
  const peak = days.reduce((a, d) => (byDay[d].eng > byDay[a].eng ? d : a), days[0]);
  const fmt = (d) => d.split("-").reverse().slice(0, 2).join("/");
  const plot = h("div", { class: "ch-plot" });
  const box = h("div", { class: "ch-box cols" },
    h("div", { class: "ch-grid" }, [1, 0.5, 0].map((f) =>
      h("div", { class: "ch-line", style: `bottom:${f * 100}%` }, h("span", {}, Math.round(max * f))))),
    plot);
  const tip = chartTip(box);
  for (const d of days) {
    const { eng, posts } = byDay[d];
    const col = h("div", { class: "ch-col", tabindex: "0", "aria-label": `${fmt(d)}: engajamento ${eng}, ${posts} posts` },
      h("div", { class: "ch-bar", style: `height:${(eng / max) * 100}%` },
        d === peak && eng > 0 ? h("span", { class: "ch-val" }, eng) : null));
    const show = () => tip.show(col, [h("b", {}, fmt(d)), h("div", {}, `Engajamento: ${eng}`), h("div", { class: "muted" }, `${posts} post(s)`)]);
    col.addEventListener("pointerenter", show);
    col.addEventListener("focus", show);
    col.addEventListener("pointerleave", tip.hide);
    col.addEventListener("blur", tip.hide);
    plot.append(col);
  }
  const mid = days[Math.floor(days.length / 2)];
  const axis = h("div", { class: "ch-axis" }, h("span", {}, fmt(days[0])),
    days.length > 2 ? h("span", {}, fmt(mid)) : null, days.length > 1 ? h("span", {}, fmt(days.at(-1))) : null);
  return h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, "Engajamento por dia"), box, axis));
}
function hourChart(rows) {
  const groups = {};
  for (const r of rows) if (r.time) (groups[r.time] ||= []).push(r);
  const items = Object.keys(groups).sort().map((t) => ({ t, v: avg(groups[t], engagement), n: groups[t].length }));
  if (!items.length) return null;
  const max = niceMax(Math.max(...items.map((i) => (typeof i.v === "number" ? i.v : 0))));
  const list = h("div", { class: "ch-hbars" });
  const box = h("div", { class: "ch-box" }, list);
  const tip = chartTip(box);
  for (const { t, v, n } of items) {
    const val = typeof v === "number" ? v : 0;
    const track = h("div", { class: "ch-track" }, h("div", { class: "ch-hbar", style: `width:${(val / max) * 100}%` }));
    const row = h("div", { class: "ch-hrow", tabindex: "0", "aria-label": `${t}: engajamento médio ${val}, ${n} posts` },
      h("span", { class: "ch-hlab" }, t), track, h("span", { class: "ch-hval" }, val));
    const show = () => tip.show(track, [h("b", {}, t), h("div", {}, `Engajamento médio: ${val}`), h("div", { class: "muted" }, `${n} post(s)`)]);
    row.addEventListener("pointerenter", show);
    row.addEventListener("focus", show);
    row.addEventListener("pointerleave", tip.hide);
    row.addEventListener("blur", tip.hide);
    list.append(row);
  }
  return h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, "Engajamento médio por horário"), box));
}

async function renderMetrics(main) {
  const refresh = h("button", { class: "btn small", onclick: async () => {
    try { await api("/api/metrics", { method: "POST", body: {} }); toast("Atualizando métricas… (~1 min, depois recarregue)"); }
    catch (e) { toast(e.message); }
  } }, "↻ Atualizar métricas");
  main.append(h("div", { class: "row", style: "margin-bottom:12px" }, refresh));
  let data;
  try { data = await api("/api/metrics"); } catch (e) { main.append(h("div", { class: "alert bad" }, e.message)); return; }
  const rows = Object.entries(data.posts || {}).map(([id, r]) => ({ id, ...r }));
  if (!rows.length) {
    main.append(h("div", { class: "empty" }, "Ainda sem métricas. Elas são coletadas a cada publicação (ou toque em Atualizar)."));
    return;
  }
  const when = data.updated_at ? new Date(data.updated_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "";
  main.append(h("p", { class: "muted" }, `${rows.length} posts dos últimos 60 dias · atualizado em ${when}. Engajamento = curtidas + 2×comentários + 3×salvamentos/compartilhamentos.`));
  for (const n of data.notes || []) main.append(h("div", { class: "alert warn" }, n));
  main.append(dailyChart(rows) || "", hourChart(rows) || "");
  main.append(retentionTable(rows) || "");
  main.append(groupTable("Por tipo de post", rows, (r) => r.type, (k) => typeName(k)));
  main.append(groupTable("Por horário", rows, (r) => r.time, (k) => k));
  const top = [...rows].sort((a, b) => engagement(b) - engagement(a)).slice(0, 10);
  main.append(h("div", { class: "card" }, h("div", { class: "sec" }, h("h3", {}, "Top 10 posts"),
    h("table", {}, h("tbody", {}, top.map((r) => h("tr", {},
      h("td", {}, h("b", {}, engagement(r))),
      h("td", {}, h("div", {}, r.title), h("div", { class: "muted" }, `${typeName(r.type)} · ${r.date?.split("-").reverse().join("/")} ${r.time}`)),
      h("td", { class: "p" }, Object.entries(r.links || {}).map(([k, u]) => h("a", { href: u, target: "_blank", rel: "noopener", style: "margin-right:6px" }, k.slice(0, 2).toUpperCase()))))))))));
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
    try { await api("/api/generate", { method: "POST", body: { compilation: true } }); toast("Gerando o vídeo longo! Leva uns 12 a 20 minutos. Depois atualize a Fila."); }
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
    h("p", { class: "muted" }, "Os posts do dia são gerados de madrugada (05:17). Com a publicação automática ligada, cada post aprovado sai no horário dele (até ~7 min depois). Use horários cheios (ex.: 12:00)."),
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
    h("p", { class: "muted" }, `Uso hoje: ${STATE.groq?.date === new Date().toISOString().slice(0, 10) ? STATE.groq.calls : 0} chamada(s).`),
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
  main.append(h("div", { class: "card" }, h("div", { class: "sec" }, f)));
}

// ---------- geral
function render() {
  const main = document.getElementById("main");
  main.replaceChildren();
  document.getElementById("brand").textContent = STATE.settings?.brand?.name || "Painel";
  if (TAB === "fila") renderQueue(main);
  else if (TAB === "historico") renderHistory(main);
  else if (TAB === "metricas") renderMetrics(main);
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
