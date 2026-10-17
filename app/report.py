"""Resumo semanal em texto (vira uma "issue" no GitHub, que chega no seu e-mail).

  python -m app.report --out resumo.md [--mention seu-usuario]
  python -m app.report --analysis [--days 28] [--apply]

Usa o state/metrics.json (curtidas, comentários, visualizações) dos últimos 7 dias
e mostra quanto conteúdo inédito ainda resta no banco (app/saturation.py).

Indicador principal: TEMPO ASSISTIDO (visualizações × tempo médio assistido), somando
Facebook, Instagram e YouTube. É o que os algoritmos de vídeo curto premiam; curtidas e
comentários aparecem só como apoio. Quando o YouTube não informa o tempo médio, usa o tempo
médio do mesmo vídeo no Facebook (estimativa).

--analysis compara os formatos no período (padrão: 28 dias), diz quais cortar e
quais concentrar, e propõe uma agenda mais enxuta. Com --apply, grava essa agenda
em config/settings.json (só com dados suficientes e fora do congelamento da grade,
schedule.frozen_until).

O resumo também traz o teste A/B de ganchos (qual frase de abertura da legenda
prende mais tempo em cada formato) e uma lista de recomendações ("corte X,
aumente Y"), além dos ajustes automáticos da grade (app/adapt.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from . import config

TYPE_NAME = {"verse": "Versículo do dia", "quiz": "Desafio de quiz", "curiosity": "Você sabia?",
             "fill": "Complete o versículo", "truefalse": "Verdadeiro ou falso", "book": "Em qual livro está?",
             "compilation": "Vídeo longo de quiz"}
MIN_POSTS_PER_HOUR = 2
# análise de formatos: abaixo disso a diferença entre formatos é ruído
MIN_POSTS_PER_TYPE = 10
MIN_TOTAL_VIEWS = 3000   # visualizações no período, somando as redes
CUT_BELOW = 0.5     # prende menos da metade da média: cortar
FOCUS_ABOVE = 1.3   # prende 30% acima da média: concentrar
MIN_POSTS_PER_HOOK = 10  # teste A/B: abaixo disso o gancho fica "em teste" (3 ou 4 posts é acaso)
HOOK_GAP = 0.6           # o pior gancho rende até 60% do melhor: vale trocar


def _n(v) -> int:
    return v if isinstance(v, (int, float)) else 0


def engagement(row: dict) -> int:
    ig, fb, yt = row.get("instagram") or {}, row.get("facebook") or {}, row.get("youtube") or {}
    return (_n(ig.get("likes")) + 2 * _n(ig.get("comments")) + 3 * _n(ig.get("saved")) + 3 * _n(ig.get("shares"))
            + _n(fb.get("likes")) + 2 * _n(fb.get("comments")) + 3 * _n(fb.get("shares"))
            + _n(yt.get("likes")) + 2 * _n(yt.get("comments")))


NETS = ("facebook", "instagram", "youtube")


def views(row: dict) -> int:
    """Visualizações somando as três redes."""
    return sum(_n((row.get(n) or {}).get("views")) for n in NETS)


def watch_seconds(row: dict) -> float | None:
    """Tempo assistido (s) somando as redes: o total informado ou visualizações × tempo médio.
    No YouTube sem tempo médio, usa o tempo médio do mesmo vídeo no Facebook.
    None quando nenhuma rede informou visualizações (ex.: post de imagem)."""
    fb_avg = (row.get("facebook") or {}).get("avg_watch_s")
    total, seen = 0.0, False
    for net in NETS:
        d = row.get(net) or {}
        if not isinstance(d.get("views"), (int, float)):
            continue
        seen = True
        if isinstance(d.get("watch_time_s"), (int, float)) and d["watch_time_s"] > 0:
            total += d["watch_time_s"]
        elif isinstance(d.get("avg_watch_s"), (int, float)):
            total += d["views"] * d["avg_watch_s"]
        elif isinstance(fb_avg, (int, float)):
            total += d["views"] * fb_avg
    return round(total, 1) if seen else None


def comments(row: dict) -> int:
    return sum(_n((row.get(n) or {}).get("comments")) for n in NETS)


def social_engagement(row: dict) -> int:
    """Só Instagram + Facebook, onde todos os formatos saem: compara formatos de forma justa
    (o YouTube só recebe alguns tipos, o que inflaria esses formatos)."""
    return engagement({k: v for k, v in row.items() if k != "youtube"})


def reach(row: dict) -> int | None:
    """Alcance: pessoas alcançadas no Instagram + visualizações no YouTube.
    None quando a rede não informou (ex.: token sem permissão de insights)."""
    ig, yt = row.get("instagram") or {}, row.get("youtube") or {}
    values = [v for v in (ig.get("reach"), yt.get("views")) if isinstance(v, (int, float))]
    return int(sum(values)) if values else None


def _avg(rows: list[dict], score=engagement) -> float:
    return round(sum(score(r) for r in rows) / len(rows), 1) if rows else 0.0


def _window(metrics: dict, today: date, days: int) -> list[dict]:
    """Posts do período para comparar formatos, ganchos e horários. Fica de fora o vídeo longo e o
    repost de domingo (app/repost.py): é o melhor post da semana de novo e inflaria o formato dele."""
    limit = (today - timedelta(days=days)).isoformat()
    return [v for v in (metrics.get("posts") or {}).values()
            if v.get("date", "") >= limit and v.get("type") not in (None, "compilation") and not v.get("repost_of")]


def _avg_watch(rows: list[dict]) -> float | None:
    vals = [w for w in (watch_seconds(r) for r in rows) if w is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def hook_analysis(metrics: dict, today: date, days: int = 28) -> dict[str, list[dict]]:
    """Teste A/B de ganchos: para cada formato, cada frase de abertura com tempo assistido e
    engajamento médios. A nota ("score") é o tempo assistido médio; sem ele, o engajamento."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in _window(metrics, today, days):
        if r.get("hook"):
            groups.setdefault((r["type"], r["hook"]), []).append(r)
    out: dict[str, list[dict]] = {}
    for (t, hook), rows in groups.items():
        out.setdefault(t, []).append({"hook": hook, "posts": len(rows), "watch": _avg_watch(rows),
                                      "engagement": _avg(rows, social_engagement)})
    for t, hooks in out.items():
        use_watch = any(h["watch"] for h in hooks)
        for h in hooks:
            h["score"] = (h["watch"] or 0) if use_watch else h["engagement"]
            h["metric"] = "tempo assistido" if use_watch else "engajamento"
        hooks.sort(key=lambda h: (h["posts"] >= MIN_POSTS_PER_HOOK, h["score"]), reverse=True)
    return out


def hooks_text(result: dict[str, list[dict]], days: int = 28) -> list[str]:
    if not result:
        return ["", "### Ganchos (teste A/B)", "",
                "Ainda sem posts com gancho registrado e métricas. O teste começa a aparecer em alguns dias."]
    lines = ["", f"### Ganchos (teste A/B, últimos {days} dias)", "",
             f"Cada post abre a legenda com um gancho sorteado. Com {MIN_POSTS_PER_HOOK}+ posts, o gancho entra "
             "na comparação; com menos, fica \"em teste\" (a diferença ainda é acaso).", ""]
    for t, hooks in sorted(result.items(), key=lambda kv: TYPE_NAME.get(kv[0], kv[0])):
        lines += [f"**{TYPE_NAME.get(t, t)}**", "", "| Gancho | Posts | Tempo assistido por post | Engajamento médio |",
                  "|---|---|---|---|"]
        for h in hooks:
            mark = "" if h["posts"] >= MIN_POSTS_PER_HOOK else " _(em teste)_"
            lines.append(f"| {h['hook']}{mark} | {h['posts']} | {_fmt_time(h['watch'])} | {h['engagement']} |")
        lines.append("")
    return lines


def _fmt_time(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds >= 3600:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 60:.1f} min" if seconds >= 120 else f"{seconds:.0f} s"


def frozen_until(settings: dict, today: date) -> str | None:
    """Data até quando a grade está congelada (schedule.frozen_until), se ainda vale."""
    until = (settings.get("schedule") or {}).get("frozen_until")
    return until if isinstance(until, str) and until >= today.isoformat() else None


def recommendations(metrics: dict, today: date, settings: dict, days: int = 28) -> list[str]:
    """O que mudar, em frases diretas: formatos, ganchos e horários (pelo tempo assistido)."""
    recs: list[str] = []
    frozen = frozen_until(settings, today)
    if frozen:
        recs.append(f"**Grade congelada até {date.fromisoformat(frozen).strftime('%d/%m')}**: as sugestões abaixo "
                    "são para anotar. Não mude horários nem formatos antes disso, senão nenhum teste conclui.")
    result = analyze(metrics, today, days)
    if not result["enough"]:
        recs.append(f"Formatos: ainda poucos dados para cortar ou aumentar ({result['views']} visualizações em "
                    f"{days} dias; mínimo {MIN_TOTAL_VIEWS}, e {MIN_POSTS_PER_TYPE} posts por formato). "
                    "Mantenha a grade.")
    in_grid = {s["type"] for s in settings.get("schedule", {}).get("slots", [])}
    for f in result["formats"]:
        name = TYPE_NAME.get(f["type"], f["type"])
        if in_grid and f["type"] not in in_grid:
            continue  # já saiu da grade
        if f["verdict"] == "cortar":
            recs.append(f"**Corte {name}**: prende {f['index']}× a média de tempo assistido ({f['posts']} posts). "
                        "Troque esses horários por um formato que prende mais.")
        elif f["verdict"] == "concentrar":
            recs.append(f"**Aumente {name}**: prende {f['index']}× a média de tempo assistido ({f['posts']} posts).")
    for t, hooks in hook_analysis(metrics, today, days).items():
        tested = [h for h in hooks if h["posts"] >= MIN_POSTS_PER_HOOK]
        if len(tested) < 2:
            continue
        best, worst = tested[0], tested[-1]
        if best["score"] > 0 and worst["score"] <= best["score"] * HOOK_GAP:
            recs.append(f"Gancho em {TYPE_NAME.get(t, t)}: “{best['hook']}” tem {best['metric']} médio "
                        f"{best['score']} contra {worst['score']} de “{worst['hook']}”. Use mais o primeiro e "
                        "aposente o segundo (em app/captions.py).")
    by_hour: dict[str, list[dict]] = {}
    for r in _window(metrics, today, days):
        if r.get("time") and watch_seconds(r) is not None:
            by_hour.setdefault(r["time"], []).append(r)
    hours = sorted(((h, _avg_watch(v)) for h, v in by_hour.items() if len(v) >= MIN_POSTS_PER_TYPE),
                   key=lambda x: x[1], reverse=True)
    if len(hours) >= 2 and hours[0][1] > 0 and hours[-1][1] <= hours[0][1] * CUT_BELOW:
        recs.append(f"Horário: o post das **{hours[-1][0]}** soma {_fmt_time(hours[-1][1])} assistidos, contra "
                    f"{_fmt_time(hours[0][1])} das **{hours[0][0]}**. Mude o das {hours[-1][0]} para perto das "
                    f"{hours[0][0]}.")
    if not any(r.startswith(("**Corte", "**Aumente", "Gancho", "Horário")) for r in recs):
        recs.append("Nada para mudar nesta semana além do que já está acima: siga com a grade atual.")
    return recs


def _adapt_lines(metrics: dict, today: date, settings: dict) -> list[str]:
    from . import adapt  # import tardio: adapt usa as contas daqui

    lines = ["", "### Grade automática", ""]
    recent = [c for c in adapt.load_history().get("changes", [])
              if c.get("date", "") >= (today - timedelta(days=7)).isoformat()]
    for c in recent:
        lines.append(f"- {c['date']}: o horário das {c['time']} passou de {TYPE_NAME.get(c['from'], c['from'])} "
                     f"para {TYPE_NAME.get(c['to'], c['to'])} ({c['reason']}).")
    plan = adapt.plan(metrics, settings, today, adapt.load_history())
    if plan.get("change"):
        c = plan["change"]
        lines.append(f"- Próximo ajuste: {c['time']} de {TYPE_NAME.get(c['from'], c['from'])} para "
                     f"{TYPE_NAME.get(c['to'], c['to'])} ({c['reason']}).")
    elif not recent:
        lines.append(f"- Sem ajuste: {plan.get('skip', 'nenhum formato com alcance zero por 2 semanas')}.")
    return lines


def _saturation_lines(today: date) -> list[str]:
    from . import saturation, state  # import tardio: saturation usa TYPE_NAME daqui

    try:
        rows = saturation.status(today, state.load_used(), config.load_settings())
    except (OSError, ValueError) as exc:
        return ["", f"> Saturação do banco indisponível: {exc}"]
    lines = ["", "### Banco de conteúdo", ""] + saturation.markdown(rows)
    return lines + [f"\n> Aviso: {w}" for w in saturation.warnings(rows)]


def retention_lines(rows: list[dict]) -> list[str]:
    """Tempo médio assistido dos vídeos no Facebook: mostra qual vídeo prende a atenção."""
    vids = [r for r in rows if isinstance((r.get("facebook") or {}).get("avg_watch_s"), (int, float))]
    if not vids:
        return []
    vids.sort(key=lambda r: r["facebook"]["avg_watch_s"], reverse=True)
    lines = ["", "### Vídeos que prendem a atenção (Facebook)", ""]
    for r in vids[:3]:
        fb = r["facebook"]
        lines.append(f"- **{fb['avg_watch_s']:.1f} s** de média: {r.get('title', r['id'])} "
                     f"({TYPE_NAME.get(r.get('type'), r.get('type'))}, {_n(fb.get('views'))} views)")
    if len(vids) > 3:
        worst = vids[-1]
        lines.append(f"- Mais fraco: {worst['facebook']['avg_watch_s']:.1f} s ({worst.get('title', worst['id'])})")
    return lines


def build(metrics: dict, today: date, mention: str = "") -> str | None:
    limit = (today - timedelta(days=7)).isoformat()
    rows = [{"id": k, **v} for k, v in (metrics.get("posts") or {}).items() if v.get("date", "") >= limit]
    if not rows:
        return None
    net_views = {n: sum(_n((r.get(n) or {}).get("views")) for r in rows) for n in NETS}
    watched = sum(w for w in (watch_seconds(r) for r in rows) if w)
    reach_ig = sum(_n((r.get("instagram") or {}).get("reach")) for r in rows)
    lines = []
    if mention:
        lines.append(f"@{mention}, o resumo da semana está pronto.\n")
    lines += [f"## Semana até {today.strftime('%d/%m/%Y')}", "",
              f"- **{len(rows)} posts** com números coletados",
              f"- **{_fmt_time(watched)}** de tempo assistido somando as redes (o indicador principal)",
              f"- Visualizações: **{net_views['facebook']}** no Facebook, **{net_views['instagram']}** no Instagram "
              f"e **{net_views['youtube']}** no YouTube",
              f"- **{reach_ig}** pessoas alcançadas no Instagram" if reach_ig else "- Alcance do Instagram: indisponível",
              f"- **{sum(comments(r) for r in rows)}** comentários somando as três redes", ""]

    try:
        settings = config.load_settings()
    except (OSError, ValueError):
        settings = {}
    lines += ["### Recomendações da semana", ""]
    lines += [f"- {r}" for r in recommendations(metrics, today, settings)]
    lines.append("")

    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r.get("type") or "?", []).append(r)
    lines += ["### Por tipo de post", "",
              "| Tipo | Posts | Tempo assistido por post | Views por post | Comentários por post |", "|---|---|---|---|---|"]
    for t, items in sorted(by_type.items(), key=lambda kv: _avg_watch(kv[1]) or -1, reverse=True):
        vids = [r for r in items if watch_seconds(r) is not None]
        per_view = round(sum(views(r) for r in vids) / len(vids), 1) if vids else "—"
        lines.append(f"| {TYPE_NAME.get(t, t)} | {len(items)} | {_fmt_time(_avg_watch(items))} | {per_view} "
                     f"| {round(sum(comments(r) for r in items) / len(items), 2)} |")

    by_hour: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("time") and watch_seconds(r) is not None:
            by_hour.setdefault(r["time"], []).append(r)
    hours = [(h, _avg_watch(v), len(v)) for h, v in by_hour.items() if len(v) >= MIN_POSTS_PER_HOUR]
    if hours:
        hours.sort(key=lambda x: x[1], reverse=True)
        best, worst = hours[0], hours[-1]
        lines += ["", "### Horários", "",
                  f"- Melhor: **{best[0]}** ({_fmt_time(best[1])} assistidos por post, {best[2]} posts)"]
        if worst[0] != best[0]:
            lines.append(f"- Mais fraco: **{worst[0]}** ({_fmt_time(worst[1])} assistidos por post, {worst[2]} posts)")

    top = sorted(rows, key=lambda r: watch_seconds(r) or 0, reverse=True)[:3]
    lines += ["", "### Os 3 vídeos mais assistidos", ""]
    for i, r in enumerate(top, start=1):
        links = " · ".join(f"[{k}]({u})" for k, u in (r.get("links") or {}).items())
        lines.append(f"{i}. **{r.get('title', r['id'])}** — {_fmt_time(watch_seconds(r))} assistidos, "
                     f"{views(r)} views ({TYPE_NAME.get(r.get('type'), r.get('type'))}, {r.get('date')} "
                     f"{r.get('time')}) {links}")

    lines += retention_lines(rows)

    long_videos = [r for r in rows if r.get("type") == "compilation"]
    for r in long_videos:
        yt = _n((r.get("youtube") or {}).get("views"))
        lines += ["", f"### Vídeo longo\n\n**{r.get('title')}**: {yt} visualizações até agora."]
    lines += hooks_text(hook_analysis(metrics, today))
    if settings:
        lines += _adapt_lines(metrics, today, settings)
    lines += _saturation_lines(today)
    for note in metrics.get("notes") or []:
        lines += ["", f"> Aviso: {note}"]
    lines += ["", "_Gerado automaticamente. Veja os gráficos completos na aba Métricas do painel._"]
    return "\n".join(lines)


def analyze(metrics: dict, today: date, days: int) -> dict:
    """Tempo assistido por formato no período e o veredito de cada um (cortar/manter/concentrar).
    Formatos sem vídeo (imagem) ficam fora da comparação: não têm tempo assistido."""
    rows = _window(metrics, today, days)
    videos = [r for r in rows if watch_seconds(r) is not None]
    overall = _avg_watch(videos) or 0.0
    total_views = sum(views(r) for r in videos)
    enough = total_views >= MIN_TOTAL_VIEWS and overall > 0
    formats = []
    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r["type"], []).append(r)
    for t, items in by_type.items():
        vids = [r for r in items if watch_seconds(r) is not None]
        watch = _avg_watch(vids)
        index = round(watch / overall, 2) if watch is not None and overall else 0.0
        fb_avg = [r["facebook"]["avg_watch_s"] for r in vids
                  if isinstance((r.get("facebook") or {}).get("avg_watch_s"), (int, float))
                  and _n(r["facebook"].get("views")) > 0]
        if watch is None:
            verdict = "sem vídeo"
        elif not enough or len(vids) < MIN_POSTS_PER_TYPE:
            verdict = "insuficiente"
        elif index < CUT_BELOW:
            verdict = "cortar"
        elif index >= FOCUS_ABOVE:
            verdict = "concentrar"
        else:
            verdict = "manter"
        net_views = {n: round(sum(_n((r.get(n) or {}).get("views")) for r in vids) / len(vids), 1)
                     for n in NETS if any(isinstance((r.get(n) or {}).get("views"), (int, float)) for r in vids)}
        formats.append({"type": t, "posts": len(items), "watch": watch, "index": index, "verdict": verdict,
                        "views": round(sum(views(r) for r in vids) / len(vids), 1) if vids else 0.0,
                        "net_views": net_views,
                        "fb_avg_watch": round(sum(fb_avg) / len(fb_avg), 1) if fb_avg else None,
                        "comments": round(sum(comments(r) for r in items) / len(items), 2),
                        "engagement": _avg(items, social_engagement)})
    formats.sort(key=lambda f: (f["watch"] is not None, f["watch"] or 0), reverse=True)
    return {"days": days, "posts": len(rows), "views": total_views, "overall": overall,
            "enough": enough, "formats": formats}


def proposed_slots(slots: list[dict], result: dict) -> list[dict]:
    """A agenda atual sem os horários dos formatos a cortar (postar menos, só o que rende).
    O Versículo do dia nunca some por inteiro: é a identidade da página."""
    cut = {f["type"] for f in result["formats"] if f["verdict"] == "cortar"}
    keep = [s for s in slots if s["type"] not in cut]
    if any(s["type"] == "verse" for s in slots) and not any(s["type"] == "verse" for s in keep):
        keep.insert(0, next(s for s in slots if s["type"] == "verse"))
    return keep or slots


def analysis_text(result: dict, slots: list[dict]) -> str:
    lines = [f"## Análise de formatos (últimos {result['days']} dias)", "",
             f"{result['posts']} posts com métricas, {result['views']} visualizações. Indicador: **tempo assistido "
             f"por post** (visualizações × tempo médio, somando Facebook, Instagram e YouTube); média "
             f"{_fmt_time(result['overall'])}.", "",
             "| Formato | Posts | Tempo assistido por post | Vs. média | Views por post (FB / IG / YT) "
             "| Tempo médio no FB | Comentários por post | Veredito |",
             "|---|---|---|---|---|---|---|---|"]
    label = {"cortar": "✂️ cortar", "concentrar": "⭐ concentrar", "manter": "manter",
             "insuficiente": "poucos dados", "sem vídeo": "imagem (fora da comparação)"}
    for f in result["formats"]:
        nv = " / ".join(str(f["net_views"].get(n, "—")) for n in NETS)
        fb = "—" if f["fb_avg_watch"] is None else f"{f['fb_avg_watch']} s"
        lines.append(f"| {TYPE_NAME.get(f['type'], f['type'])} | {f['posts']} | {_fmt_time(f['watch'])} "
                     f"| {f['index']}× | {nv} | {fb} | {f['comments']} | {label[f['verdict']]} |")
    measured = {f["type"] for f in result["formats"]}
    for t in dict.fromkeys(s["type"] for s in slots):
        if t not in measured:
            lines.append(f"| {TYPE_NAME.get(t, t)} | 0 | — | — | — | — | — | sem métricas ainda (fica) |")
    if not result["enough"]:
        lines += ["", f"**Ainda não dá para decidir:** são {result['views']} visualizações no período "
                  f"(mínimo {MIN_TOTAL_VIEWS}). Mantenha a agenda e rode de novo daqui a 1 ou 2 semanas."]
        return "\n".join(lines)
    new = proposed_slots(slots, result)
    if len(new) == len(slots):
        lines += ["", "Nenhum formato prende muito abaixo da média: a agenda atual pode ficar."]
    else:
        lines += ["", f"**Proposta:** de {len(slots)} para {len(new)} posts por dia, sem os formatos marcados "
                  "para cortar. Menos posts, todos dos formatos que prendem, costuma ajudar o alcance.", "",
                  "```json", json.dumps(new, ensure_ascii=False), "```", "",
                  "Para aplicar (depois do congelamento da grade): `python -m app.report --analysis --apply`."]
    focus = [TYPE_NAME.get(f["type"], f["type"]) for f in result["formats"] if f["verdict"] == "concentrar"]
    if focus:
        lines += ["", f"Formatos que mais prendem: **{', '.join(focus)}**. Se for trocar algum horário, "
                  "troque por eles."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.report")
    parser.add_argument("--out", default="resumo.md")
    parser.add_argument("--mention", default="")
    parser.add_argument("--date")
    parser.add_argument("--analysis", action="store_true", help="compara formatos e propõe a agenda")
    parser.add_argument("--days", type=int, default=28, help="período da análise (padrão: 28)")
    parser.add_argument("--apply", action="store_true", help="com --analysis: grava a agenda proposta")
    args = parser.parse_args(argv)
    path = config.STATE_DIR / "metrics.json"
    metrics = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    today = date.fromisoformat(args.date) if args.date else date.today()
    if args.analysis:
        settings = config.load_settings()
        slots = settings["schedule"]["slots"]
        result = analyze(metrics, today, args.days)
        print(analysis_text(result, slots))
        print("\n".join(hooks_text(hook_analysis(metrics, today, args.days), args.days)))
        print("\n### Recomendações\n")
        print("\n".join(f"- {r}" for r in recommendations(metrics, today, settings, args.days)))
        new = proposed_slots(slots, result)
        frozen = frozen_until(settings, today)
        if args.apply and frozen:
            print(f"\nNada gravado: a grade está congelada até {frozen} (schedule.frozen_until).")
        elif args.apply and result["enough"] and len(new) < len(slots):
            settings["schedule"] = {**settings["schedule"], "slots": new}
            config.CONFIG_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=1) + "\n",
                                          encoding="utf-8")
            print(f"\nAgenda gravada em {config.CONFIG_PATH.relative_to(config.ROOT)}: {len(new)} posts por dia.")
        elif args.apply:
            print("\nNada gravado: sem dados suficientes ou sem formato para cortar.")
        return 0
    text = build(metrics, today, args.mention)
    if not text:
        print("Sem métricas na última semana: resumo não gerado.")
        return 1
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"resumo salvo em {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
