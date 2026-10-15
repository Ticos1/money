"""Mini-site público: versículo do dia + quiz de hoje (sem login).

  python -m app.site --out dist [--base-url https://seu-projeto.pages.dev] [--date 2026-10-15]

Gera páginas estáticas a partir da fila e do histórico (state/), junto com o painel
no Cloudflare Pages:
  /hoje/              versículo + quiz do dia (o link para colocar na bio)
  /dia/AAAA-MM-DD/    página fixa de cada dia (o Google indexa uma por dia)
  /dia/               arquivo com todos os dias
  /robots.txt, /sitemap.xml
O painel continua protegido por login (dashboard/functions/_middleware.js libera só
essas páginas e as imagens do versículo, usadas na prévia do link).
Só usa a biblioteca padrão: roda também no deploy, que não instala dependências.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import bible, config, state

MAX_QUIZZES = 5
LETTERS = "ABCD"
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
          "outubro", "novembro", "dezembro"]
WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
VERSE_IMAGES = ("imagem_quadrada.jpg", "imagem_vertical.jpg", "imagem_story.jpg")

e = html.escape


def long_date(day: str) -> str:
    d = date.fromisoformat(day)
    return f"{WEEKDAYS[d.weekday()]}, {d.day} de {MONTHS[d.month - 1]} de {d.year}"


def collect(posts: list[dict], today: date) -> dict[str, dict]:
    """{dia: {"verse": conteúdo|None, "quizzes": [...], "image": url|None}} só com dias até hoje."""
    by_day: dict[str, list[dict]] = {}
    for p in posts:
        if p.get("status") == "rejected" or p.get("date", "") > today.isoformat():
            continue
        by_day.setdefault(p["date"], []).append(p)
    days = {}
    for day, items in by_day.items():
        items.sort(key=lambda p: (p.get("slot", 99), p.get("created_at", "")))
        verse_post = next((p for p in items if p.get("type") == "verse"
                           and (p.get("content") or {}).get("verse_text")), None)
        quizzes, seen = [], set()
        for p in items:
            c = p.get("content") or {}
            if p.get("type") != "quiz" or not c.get("question") or len(c.get("options") or []) != 4:
                continue
            if not isinstance(c.get("answer"), int) or c["question"] in seen:
                continue
            seen.add(c["question"])
            quizzes.append(c)
            if len(quizzes) == MAX_QUIZZES:
                break
        if not verse_post and not quizzes:
            continue
        image = None
        if verse_post:
            media = verse_post.get("media") or {}
            name = next((f for f in VERSE_IMAGES if f in (media.get("images") or [])), None)
            if name and media.get("base"):
                image = "/" + media["base"].strip("/") + "/" + name
        days[day] = {"verse": (verse_post or {}).get("content"), "quizzes": quizzes, "image": image}
    return dict(sorted(days.items(), reverse=True))


# ---------------------------------------------------------------- HTML

CSS = """
:root{--bg:#f7f3ec;--card:#fff;--ink:#1d1b26;--muted:#6b6577;--accent:#7a4bd6;--gold:#c8902a;
--ok:#1f9d55;--bad:#d23c3c;--line:#e7e1d6}
@media (prefers-color-scheme:dark){:root{--bg:#14121b;--card:#1f1c29;--ink:#f2eff8;--muted:#a59fb3;
--accent:#a98bf0;--gold:#f0c060;--line:#2e2a3b}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:680px;margin:0 auto;padding:20px 16px 48px}
header{text-align:center;margin:8px 0 20px}
header .brand{font-weight:800;letter-spacing:.04em;text-transform:uppercase;font-size:14px;color:var(--accent);text-decoration:none}
header h1{font-size:26px;line-height:1.25;margin:6px 0 2px}
header p{margin:0;color:var(--muted);font-size:15px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px;margin:16px 0;
box-shadow:0 6px 24px rgba(30,20,60,.06)}
.tag{display:inline-block;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;
color:var(--gold);margin-bottom:8px}
blockquote{margin:0;font:600 24px/1.45 Georgia,"Times New Roman",serif}
.ref{margin:10px 0 0;font-weight:700;color:var(--accent)}
.reflection{margin:14px 0 0;color:var(--muted)}
.q{margin:0 0 12px;font-weight:700;font-size:19px;line-height:1.4}
.opts{display:grid;gap:10px}
.opts button{all:unset;cursor:pointer;display:flex;gap:12px;align-items:center;padding:13px 16px;
border:2px solid var(--line);border-radius:14px;font-weight:600;background:var(--card);color:var(--ink)}
.opts button:hover,.opts button:focus-visible{border-color:var(--accent)}
.opts b{display:inline-grid;place-items:center;min-width:30px;height:30px;border-radius:50%;
background:var(--accent);color:#fff;font-size:14px}
.opts button.right{border-color:var(--ok);background:color-mix(in srgb,var(--ok) 14%,var(--card))}
.opts button.right b{background:var(--ok)}
.opts button.wrong{border-color:var(--bad);opacity:.85}.opts button.wrong b{background:var(--bad)}
.opts button[disabled]{cursor:default}
.answer{display:none;margin-top:12px;padding:12px 14px;border-radius:12px;background:var(--bg);font-size:15px}
.answer.show{display:block}
.score{text-align:center;font-weight:800;font-size:18px;margin:6px 0}
.actions{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin:18px 0}
.btn{display:inline-block;padding:11px 18px;border-radius:999px;background:var(--accent);color:#fff;
font-weight:700;text-decoration:none;border:0;font-size:15px;cursor:pointer}
.btn.alt{background:transparent;color:var(--accent);border:2px solid var(--accent)}
.days{list-style:none;padding:0;margin:0}.days li{padding:10px 0;border-bottom:1px solid var(--line)}
.days a{color:var(--ink);text-decoration:none;font-weight:600}.days span{display:block;color:var(--muted);font-size:14px}
footer{text-align:center;color:var(--muted);font-size:13px;margin-top:28px}
footer a{color:var(--muted)}
"""

JS = """
(function(){var total=document.querySelectorAll('.quiz').length,done=0,ok=0,s=document.getElementById('score');
document.querySelectorAll('.quiz').forEach(function(q){var a=+q.dataset.a;
q.querySelectorAll('.opts button').forEach(function(b,i){b.addEventListener('click',function(){
if(q.dataset.done)return;q.dataset.done=1;done++;if(i===a)ok++;
q.querySelectorAll('.opts button').forEach(function(x,j){x.disabled=true;if(j===a)x.classList.add('right');
else if(j===i)x.classList.add('wrong');});
var r=q.querySelector('.answer');r.querySelector('strong').textContent=i===a?'Você acertou! 🎉':'Quase! ';
r.classList.add('show');if(s&&done===total){s.textContent='Você acertou '+ok+' de '+total+'!';s.hidden=false;}
});});});
var sh=document.getElementById('share');if(sh)sh.addEventListener('click',function(){
var d={title:document.title,text:sh.dataset.text,url:location.href};
if(navigator.share){navigator.share(d).catch(function(){});}else{navigator.clipboard&&navigator.clipboard.writeText(location.href);sh.textContent='Link copiado!';}
});})();
"""


def _page(title: str, description: str, body: str, canonical: str, image: str | None, brand: dict,
          base_url: str, jsonld: dict | None = None) -> str:
    abs_url = f"{base_url}{canonical}" if base_url else canonical
    meta = [f'<link rel="canonical" href="{e(abs_url)}">',
            f'<meta property="og:title" content="{e(title)}">',
            f'<meta property="og:description" content="{e(description)}">',
            f'<meta property="og:url" content="{e(abs_url)}">',
            '<meta property="og:type" content="article">',
            f'<meta property="og:site_name" content="{e(brand.get("name", ""))}">',
            '<meta property="og:locale" content="pt_BR">',
            '<meta name="twitter:card" content="summary_large_image">']
    if image:
        meta.append(f'<meta property="og:image" content="{e((base_url or "") + image)}">')
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
{chr(10).join(meta)}
<link rel="icon" href="/icon.svg"><link rel="stylesheet" href="/hoje/site.css">
{ld}
</head>
<body><main>
{body}
<footer>
<p><a href="/hoje/">Hoje</a> · <a href="/dia/">Dias anteriores</a> · <a href="/sobre">Sobre</a> · <a href="/privacidade">Privacidade</a></p>
<p>Texto bíblico: {e(bible.TRANSLATION_NAME)} (domínio público).</p>
</footer>
</main>
<script src="/hoje/site.js" defer></script>
</body></html>
"""


def _header(brand: dict, day: str, heading: str) -> str:
    return (f'<header><a class="brand" href="/hoje/">{e(brand.get("name", ""))}</a>'
            f'<h1>{e(heading)}</h1><p>{e(long_date(day))}</p></header>')


def _verse_html(v: dict) -> str:
    return (f'<section class="card"><div class="tag">Versículo do dia</div>'
            f'<blockquote>“{e(v["verse_text"])}”</blockquote>'
            f'<p class="ref">{e(v.get("ref_label") or v.get("ref", ""))}</p>'
            + (f'<p class="reflection">{e(v["reflection"])}</p>' if v.get("reflection") else "")
            + "</section>")


def _quiz_html(quizzes: list[dict]) -> str:
    out = []
    for n, q in enumerate(quizzes, start=1):
        opts = "".join(f'<button type="button"><b>{LETTERS[i]}</b><span>{e(o)}</span></button>'
                       for i, o in enumerate(q["options"]))
        right = f'{LETTERS[q["answer"]]}) {q["options"][q["answer"]]}'
        passage = f' “{e(q["passage"])}”' if q.get("passage") else ""
        out.append(
            f'<section class="card quiz" data-a="{int(q["answer"])}">'
            f'<div class="tag">Quiz bíblico · pergunta {n} de {len(quizzes)}</div>'
            f'<p class="q">{e(q["question"])}</p><div class="opts">{opts}</div>'
            f'<div class="answer"><strong></strong> Resposta: <b>{e(right)}</b>. '
            f'{e(q.get("ref_label") or q.get("ref", ""))}:{passage}</div></section>')
    return "".join(out) + '<p class="score" id="score" hidden></p>' if out else ""


def _jsonld(day: str, data: dict, url: str, brand: dict) -> dict:
    parts = []
    for q in data["quizzes"]:
        parts.append({"@type": "Question", "name": q["question"], "eduQuestionType": "Multiple choice",
                      "acceptedAnswer": {"@type": "Answer", "text": q["options"][q["answer"]]},
                      "suggestedAnswer": [{"@type": "Answer", "text": o}
                                          for i, o in enumerate(q["options"]) if i != q["answer"]]})
    ld = {"@context": "https://schema.org", "@type": "WebPage", "url": url, "inLanguage": "pt-BR",
          "datePublished": day, "name": f"Versículo do dia e quiz bíblico · {long_date(day)}",
          "publisher": {"@type": "Organization", "name": brand.get("name", "")}}
    if parts:
        ld["mainEntity"] = {"@type": "Quiz", "name": "Quiz bíblico do dia", "about": "Bíblia",
                            "hasPart": parts}
    return ld


def day_page(day: str, data: dict, brand: dict, base_url: str, canonical: str, heading: str) -> str:
    v = data["verse"]
    if v:
        title = f"Versículo do dia: {v.get('ref_label', '')} · {brand.get('name', '')}"
        desc = f"“{v['verse_text']}” ({v.get('ref_label', '')}). Leia a reflexão e faça o quiz bíblico de hoje."
    else:
        title = f"Quiz bíblico do dia · {brand.get('name', '')}"
        desc = f"{len(data['quizzes'])} perguntas da Bíblia para testar o seu conhecimento hoje."
    share_text = f"Versículo do dia e quiz bíblico: quantas você acerta?"
    handle = brand.get("handle", "")
    body = (_header(brand, day, heading)
            + (_verse_html(v) if v else "")
            + (('<h2 style="text-align:center;margin:28px 0 0">Quiz de hoje: quantas você acerta?</h2>'
                + _quiz_html(data["quizzes"])) if data["quizzes"] else "")
            + '<div class="actions">'
            + f'<button class="btn" id="share" data-text="{e(share_text)}">Compartilhar</button>'
            + f'<a class="btn alt" href="https://wa.me/?text={e(_urlquote(share_text + " " + (base_url + canonical)))}" '
              'rel="noopener" target="_blank">Enviar no WhatsApp</a>'
            + "</div>"
            + (f'<p style="text-align:center;color:var(--muted)">Todo dia tem versículo e quiz novos. '
               f'Siga <b>{e(handle)}</b> nas redes.</p>' if handle else ""))
    url = (base_url or "") + canonical
    desc = desc if len(desc) <= 300 else desc[:297].rsplit(" ", 1)[0] + "…"
    return _page(title, desc, body, canonical, data["image"], brand, base_url, _jsonld(day, data, url, brand))


def _urlquote(text: str) -> str:
    from urllib.parse import quote
    return quote(text, safe="")


def archive_page(days: dict[str, dict], brand: dict, base_url: str) -> str:
    items = []
    for day, data in days.items():
        v = data["verse"]
        sub = f'{v.get("ref_label", "")}: {v.get("on_screen") or v["verse_text"][:90]}' if v else \
            f'{len(data["quizzes"])} perguntas de quiz'
        items.append(f'<li><a href="/dia/{day}/">{e(long_date(day))}</a><span>{e(sub)}</span></li>')
    body = (f'<header><a class="brand" href="/hoje/">{e(brand.get("name", ""))}</a>'
            '<h1>Versículos e quizzes anteriores</h1></header>'
            f'<section class="card"><ul class="days">{"".join(items)}</ul></section>')
    return _page(f"Versículos do dia anteriores · {brand.get('name', '')}",
                 "Arquivo com os versículos do dia e os quizzes bíblicos já publicados.", body, "/dia/", None,
                 brand, base_url)


def build(out: Path, base_url: str, today: date, posts: list[dict], brand: dict) -> list[str]:
    """Grava o site em out/ e devolve as URLs (para o sitemap)."""
    base_url = base_url.rstrip("/")
    days = collect(posts, today)
    (out / "hoje").mkdir(parents=True, exist_ok=True)
    (out / "hoje" / "site.css").write_text(CSS.strip() + "\n", encoding="utf-8")
    (out / "hoje" / "site.js").write_text(JS.strip() + "\n", encoding="utf-8")
    urls = []
    if days:
        latest, data = next(iter(days.items()))
        (out / "hoje" / "index.html").write_text(
            day_page(latest, data, brand, base_url, "/hoje/", "Versículo do dia e quiz bíblico"), encoding="utf-8")
        urls.append("/hoje/")
    else:
        (out / "hoje" / "index.html").write_text(_page(
            brand.get("name", ""), "Versículo do dia e quiz bíblico.",
            "<header><h1>Volte amanhã cedo</h1><p>O versículo do dia sai todas as manhãs.</p></header>",
            "/hoje/", None, brand, base_url), encoding="utf-8")
    for day, data in days.items():
        d = out / "dia" / day
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(
            day_page(day, data, brand, base_url, f"/dia/{day}/", "Versículo do dia e quiz bíblico"),
            encoding="utf-8")
        urls.append(f"/dia/{day}/")
    (out / "dia").mkdir(parents=True, exist_ok=True)
    (out / "dia" / "index.html").write_text(archive_page(days, brand, base_url), encoding="utf-8")
    urls.append("/dia/")

    robots = ["User-agent: *", "Allow: /hoje/", "Allow: /dia/", "Allow: /media/", "Disallow: /"]
    if base_url:
        robots.append(f"Sitemap: {base_url}/sitemap.xml")
        last = {u: u.split("/")[2] if u.startswith("/dia/2") else (next(iter(days), today.isoformat()))
                for u in urls}
        sm = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        sm += [f"<url><loc>{e(base_url + u)}</loc><lastmod>{last[u]}</lastmod></url>" for u in urls]
        sm.append("</urlset>")
        (out / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")
    (out / "robots.txt").write_text("\n".join(robots) + "\n", encoding="utf-8")
    return urls


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.site")
    parser.add_argument("--out", default="dist")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--date")
    args = parser.parse_args(argv)
    settings = json.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))
    tz = ZoneInfo(settings.get("timezone", "America/Sao_Paulo"))
    today = date.fromisoformat(args.date) if args.date else datetime.now(tz).date()
    urls = build(Path(args.out), args.base_url, today, state.load_queue() + state.load_history(),
                 settings.get("brand", {}))
    print(f"mini-site: {len(urls)} página(s) em {args.out}/ (hoje, {max(0, len(urls) - 2)} dia(s) e arquivo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
