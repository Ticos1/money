"""Saturação do banco: quanto conteúdo inédito ainda resta para cada formato.

  python -m app.saturation [--date 2026-10-15]

Cruza o banco (content/bank) com o state/used.json usando as mesmas regras de
escolha da geração e divide o que sobra pelo consumo diário da agenda
(config/settings.json). É uma estimativa sem a IA: o conteúdo novo da Groq só
aumenta o prazo.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date

from . import config, content, derived, state
from .report import TYPE_NAME

# quem gasta os itens que cada formato considera "já usados":
# o Verdadeiro ou falso marca a pergunta como usada também no quiz (e vice-versa)
CONSUMERS = {"verse": ("verse",), "fill": ("fill",), "quiz": ("quiz", "truefalse"),
             "truefalse": ("truefalse", "quiz"), "curiosity": ("curiosity",)}
REPEATS_AFTER = {"fill": derived.RECENT_DAYS, "truefalse": derived.RECENT_DAYS}  # demais: nunca repetem
WARN_DAYS = 30


def per_day(settings: dict) -> Counter:
    return Counter(slot["type"] for slot in settings.get("schedule", {}).get("slots", []))


def status(today: date, used: dict, settings: dict) -> list[dict]:
    daily = per_day(settings)
    rows = []
    for kind, consumers in CONSUMERS.items():
        if kind in derived.KINDS:
            bank, fresh = derived.bank_status(kind, today, used)
        else:
            bank, fresh = content.bank_status(kind, today, used)
        if kind == "fill":  # só conta o versículo que dá para transformar em "Complete"
            bank = [i for i in bank if derived.fill_ready(i)]
            fresh = [i for i in fresh if derived.fill_ready(i)]
        rate = sum(daily[c] for c in consumers)
        rows.append({
            "kind": kind,
            "bank": len(bank),
            "fresh": len(fresh),
            "saturation": round(100 * (1 - len(fresh) / len(bank))) if bank else 100,
            "per_day": daily[kind],
            "days_left": len(fresh) // rate if rate else None,
            "repeats_after": REPEATS_AFTER.get(kind),
        })
    return rows


def warnings(rows: list[dict]) -> list[str]:
    out = []
    for r in rows:
        if r["per_day"] and r["days_left"] is not None and r["days_left"] < WARN_DAYS:
            out.append(f"{TYPE_NAME[r['kind']]}: só {r['days_left']} dias de conteúdo inédito; "
                       "amplie o banco ou reduza esse formato na agenda.")
    return out


def markdown(rows: list[dict]) -> list[str]:
    lines = ["| Formato | Na agenda/dia | Banco | Inéditos | Saturação | Dias até repetir |",
             "|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["days_left"] is None, r["days_left"] or 0)):
        days = "—" if r["days_left"] is None else str(r["days_left"])
        if r["per_day"] and r["days_left"] is not None and r["days_left"] < WARN_DAYS:
            days = f"⚠️ {days}"
        lines.append(f"| {TYPE_NAME[r['kind']]} | {r['per_day']} | {r['bank']} | {r['fresh']} "
                     f"| {r['saturation']}% | {days} |")
    lines += ["", "_Sem contar o conteúdo novo da IA. \"Complete o versículo\" e \"Verdadeiro ou falso\" "
              f"podem repetir um item depois de {derived.RECENT_DAYS} dias; os demais formatos não repetem._"]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.saturation")
    parser.add_argument("--date")
    args = parser.parse_args(argv)
    today = date.fromisoformat(args.date) if args.date else date.today()
    rows = status(today, state.load_used(), config.load_settings())
    print("\n".join(markdown(rows)))
    for w in warnings(rows):
        print(f"\nAviso: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
