"""Resumo semanal em texto (vira uma "issue" no GitHub, que chega no seu e-mail).

  python -m app.report --out resumo.md [--mention seu-usuario]

Usa o state/metrics.json (curtidas, comentários, visualizações) dos últimos 7 dias.
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


def _n(v) -> int:
    return v if isinstance(v, (int, float)) else 0


def engagement(row: dict) -> int:
    ig, fb, yt = row.get("instagram") or {}, row.get("facebook") or {}, row.get("youtube") or {}
    return (_n(ig.get("likes")) + 2 * _n(ig.get("comments")) + 3 * _n(ig.get("saved")) + 3 * _n(ig.get("shares"))
            + _n(fb.get("likes")) + 2 * _n(fb.get("comments")) + 3 * _n(fb.get("shares"))
            + _n(yt.get("likes")) + 2 * _n(yt.get("comments")))


def _avg(rows: list[dict]) -> float:
    return round(sum(engagement(r) for r in rows) / len(rows), 1) if rows else 0.0


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
    for note in metrics.get("notes") or []:
        lines += ["", f"> Aviso: {note}"]
    lines += ["", "_Gerado automaticamente. Veja os gráficos completos na aba Métricas do painel._"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.report")
    parser.add_argument("--out", default="resumo.md")
    parser.add_argument("--mention", default="")
    parser.add_argument("--date")
    args = parser.parse_args(argv)
    path = config.STATE_DIR / "metrics.json"
    metrics = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    text = build(metrics, date.fromisoformat(args.date) if args.date else date.today(), args.mention)
    if not text:
        print("Sem métricas na última semana: resumo não gerado.")
        return 1
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"resumo salvo em {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
