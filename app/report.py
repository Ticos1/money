"""Resumo semanal em texto (vira uma "issue" no GitHub, que chega no seu e-mail).

  python -m app.report --out resumo.md [--mention seu-usuario]
  python -m app.report --analysis [--days 28] [--apply]

Usa o state/metrics.json (curtidas, comentários, visualizações) dos últimos 7 dias
e mostra quanto conteúdo inédito ainda resta no banco (app/saturation.py).

--analysis compara os formatos no período (padrão: 28 dias), diz quais cortar e
quais concentrar, e propõe uma agenda mais enxuta. Com --apply, grava essa agenda
em config/settings.json (só quando há dados suficientes para decidir).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from . import config

TYPE_NAME = {"verse": "Versículo do dia", "quiz": "Desafio de quiz", "curiosity": "Você sabia?",
             "fill": "Complete o versículo", "truefalse": "Verdadeiro ou falso",
             "compilation": "Vídeo longo de quiz"}
MIN_POSTS_PER_HOUR = 2
# análise de formatos: abaixo disso a diferença entre formatos é ruído
MIN_POSTS_PER_TYPE = 6
MIN_TOTAL_ENGAGEMENT = 30
CUT_BELOW = 0.5     # rende menos da metade da média: cortar
FOCUS_ABOVE = 1.3   # rende 30% acima da média: concentrar


def _n(v) -> int:
    return v if isinstance(v, (int, float)) else 0


def engagement(row: dict) -> int:
    ig, fb, yt = row.get("instagram") or {}, row.get("facebook") or {}, row.get("youtube") or {}
    return (_n(ig.get("likes")) + 2 * _n(ig.get("comments")) + 3 * _n(ig.get("saved")) + 3 * _n(ig.get("shares"))
            + _n(fb.get("likes")) + 2 * _n(fb.get("comments")) + 3 * _n(fb.get("shares"))
            + _n(yt.get("likes")) + 2 * _n(yt.get("comments")))


def social_engagement(row: dict) -> int:
    """Só Instagram + Facebook, onde todos os formatos saem: compara formatos de forma justa
    (o YouTube só recebe alguns tipos, o que inflaria esses formatos)."""
    return engagement({k: v for k, v in row.items() if k != "youtube"})


def _avg(rows: list[dict], score=engagement) -> float:
    return round(sum(score(r) for r in rows) / len(rows), 1) if rows else 0.0


def _saturation_lines(today: date) -> list[str]:
    from . import saturation, state  # import tardio: saturation usa TYPE_NAME daqui

    try:
        rows = saturation.status(today, state.load_used(), config.load_settings())
    except (OSError, ValueError) as exc:
        return ["", f"> Saturação do banco indisponível: {exc}"]
    lines = ["", "### Banco de conteúdo", ""] + saturation.markdown(rows)
    return lines + [f"\n> Aviso: {w}" for w in saturation.warnings(rows)]


def build(metrics: dict, today: date, mention: str = "") -> str | None:
    limit = (today - timedelta(days=7)).isoformat()
    rows = [{"id": k, **v} for k, v in (metrics.get("posts") or {}).items() if v.get("date", "") >= limit]
    if not rows:
        return None
    yt_views = sum(_n((r.get("youtube") or {}).get("views")) for r in rows)
    reach = sum(_n((r.get("instagram") or {}).get("reach")) for r in rows)
    likes = sum(_n((r.get("instagram") or {}).get("likes")) + _n((r.get("facebook") or {}).get("likes"))
                + _n((r.get("youtube") or {}).get("likes")) for r in rows)
    lines = []
    if mention:
        lines.append(f"@{mention}, o resumo da semana está pronto.\n")
    lines += [f"## Semana até {today.strftime('%d/%m/%Y')}", "",
              f"- **{len(rows)} posts** com números coletados",
              f"- **{yt_views}** visualizações no YouTube",
              f"- **{reach}** pessoas alcançadas no Instagram" if reach else "- Alcance do Instagram: indisponível",
              f"- **{likes}** curtidas somando as três redes", ""]

    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r.get("type") or "?", []).append(r)
    lines += ["### Por tipo de post", "", "| Tipo | Posts | Engajamento médio |", "|---|---|---|"]
    for t, items in sorted(by_type.items(), key=lambda kv: _avg(kv[1]), reverse=True):
        lines.append(f"| {TYPE_NAME.get(t, t)} | {len(items)} | {_avg(items)} |")

    by_hour: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("time"):
            by_hour.setdefault(r["time"], []).append(r)
    hours = [(h, _avg(v), len(v)) for h, v in by_hour.items() if len(v) >= MIN_POSTS_PER_HOUR]
    if hours:
        hours.sort(key=lambda x: x[1], reverse=True)
        best, worst = hours[0], hours[-1]
        lines += ["", "### Horários", "",
                  f"- Melhor: **{best[0]}** (engajamento médio {best[1]}, {best[2]} posts)"]
        if worst[0] != best[0]:
            lines.append(f"- Mais fraco: **{worst[0]}** (engajamento médio {worst[1]}, {worst[2]} posts)")

    top = sorted(rows, key=engagement, reverse=True)[:3]
    lines += ["", "### Os 3 melhores posts", ""]
    for i, r in enumerate(top, start=1):
        links = " · ".join(f"[{k}]({u})" for k, u in (r.get("links") or {}).items())
        lines.append(f"{i}. **{r.get('title', r['id'])}** — engajamento {engagement(r)} "
                     f"({TYPE_NAME.get(r.get('type'), r.get('type'))}, {r.get('date')} {r.get('time')}) {links}")

    long_videos = [r for r in rows if r.get("type") == "compilation"]
    for r in long_videos:
        views = _n((r.get("youtube") or {}).get("views"))
        lines += ["", f"### Vídeo longo\n\n**{r.get('title')}**: {views} visualizações até agora."]
    lines += _saturation_lines(today)
    for note in metrics.get("notes") or []:
        lines += ["", f"> Aviso: {note}"]
    lines += ["", "_Gerado automaticamente. Veja os gráficos completos na aba Métricas do painel._"]
    return "\n".join(lines)


def analyze(metrics: dict, today: date, days: int) -> dict:
    """Engajamento por formato no período e o veredito de cada um (cortar/manter/concentrar)."""
    limit = (today - timedelta(days=days)).isoformat()
    rows = [v for v in (metrics.get("posts") or {}).values()
            if v.get("date", "") >= limit and v.get("type") not in (None, "compilation")]
    overall = _avg(rows, social_engagement)
    total = sum(social_engagement(r) for r in rows)
    enough = total >= MIN_TOTAL_ENGAGEMENT and overall > 0
    formats = []
    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r["type"], []).append(r)
    for t, items in by_type.items():
        avg = _avg(items, social_engagement)
        index = round(avg / overall, 2) if overall else 0.0
        yt = [r for r in items if r.get("youtube")]
        if not enough or len(items) < MIN_POSTS_PER_TYPE:
            verdict = "insuficiente"
        elif index < CUT_BELOW:
            verdict = "cortar"
        elif index >= FOCUS_ABOVE:
            verdict = "concentrar"
        else:
            verdict = "manter"
        formats.append({"type": t, "posts": len(items), "avg": avg, "index": index, "verdict": verdict,
                        "yt_views": round(sum(_n(r["youtube"].get("views")) for r in yt) / len(yt), 1)
                        if yt else None})
    formats.sort(key=lambda f: f["avg"], reverse=True)
    return {"days": days, "posts": len(rows), "total": total, "overall": overall,
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
             f"{result['posts']} posts com métricas, engajamento médio {result['overall']} por post "
             "(Instagram + Facebook: curtida 1, comentário 2, salvamento e compartilhamento 3).", "",
             "| Formato | Posts | Engajamento médio | Vs. média | Views médias no YouTube | Veredito |",
             "|---|---|---|---|---|---|"]
    label = {"cortar": "✂️ cortar", "concentrar": "⭐ concentrar", "manter": "manter",
             "insuficiente": "poucos dados"}
    for f in result["formats"]:
        yt = "—" if f["yt_views"] is None else f["yt_views"]
        lines.append(f"| {TYPE_NAME.get(f['type'], f['type'])} | {f['posts']} | {f['avg']} "
                     f"| {f['index']}× | {yt} | {label[f['verdict']]} |")
    measured = {f["type"] for f in result["formats"]}
    for t in dict.fromkeys(s["type"] for s in slots):
        if t not in measured:
            lines.append(f"| {TYPE_NAME.get(t, t)} | 0 | — | — | — | sem métricas ainda (fica) |")
    if not result["enough"]:
        lines += ["", f"**Ainda não dá para decidir:** são {result['total']} interações no período "
                  f"(mínimo {MIN_TOTAL_ENGAGEMENT}). Com tão pouco, a diferença entre formatos é acaso. "
                  "Mantenha a agenda e rode de novo daqui a 1 ou 2 semanas."]
        return "\n".join(lines)
    new = proposed_slots(slots, result)
    if len(new) == len(slots):
        lines += ["", "Nenhum formato rende muito abaixo da média: a agenda atual pode ficar."]
    else:
        lines += ["", f"**Proposta:** de {len(slots)} para {len(new)} posts por dia, sem os formatos marcados "
                  "para cortar. Menos posts, todos dos formatos que rendem, costuma ajudar o alcance.", "",
                  "```json", json.dumps(new, ensure_ascii=False), "```", "",
                  "Para aplicar: `python -m app.report --analysis --apply` (ou ajuste os horários no painel)."]
    focus = [TYPE_NAME.get(f["type"], f["type"]) for f in result["formats"] if f["verdict"] == "concentrar"]
    if focus:
        lines += ["", f"Formatos que mais rendem: **{', '.join(focus)}**. Se for trocar algum horário, "
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
        new = proposed_slots(slots, result)
        if args.apply and result["enough"] and len(new) < len(slots):
            settings["schedule"]["slots"] = new
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
