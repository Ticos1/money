"""Grade que se adapta ao desempenho: aposta mais no que funciona, sem reescrever a agenda.

  python -m app.adapt            # só mostra o que faria
  python -m app.adapt --apply    # grava em config/settings.json (usado no GitHub Actions)

Regra: se um formato passa 2 semanas (adapt.zero_days) com ALCANCE ZERO em todos os posts
medidos, um dos horários dele passa para o formato que mais alcança. Assim:
- o total de posts por dia não muda;
- o primeiro horário (Versículo do dia) nunca é mexido;
- cada formato fica com pelo menos 1 horário (continua sendo medido);
- o Versículo não ganha horário extra (é 1 por dia) e não entra formato cujo banco está acabando;
- no máximo 1 ajuste a cada adapt.cooldown_days (padrão 14), para dar tempo de medir.

Cada ajuste fica registrado em state/adapt.json e aparece no resumo semanal.
Para desligar: "adapt": {"enabled": false} em config/settings.json.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import date, timedelta

from . import config, report

DEFAULTS = {"enabled": True, "zero_days": 14, "cooldown_days": 14, "min_posts": 6}
HISTORY_FILE = "adapt.json"


def settings_for(settings: dict) -> dict:
    return {**DEFAULTS, **(settings.get("adapt") or {})}


def load_history() -> dict:
    path = config.STATE_DIR / HISTORY_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"changes": []}


def _signal(row: dict) -> int | None:
    """Alcance + interações. None = sem dado de alcance (não conta como zero)."""
    r = report.reach(row)
    return None if r is None else r + report.engagement(row)


def performance(metrics: dict, today: date, days: int) -> dict[str, dict]:
    """Por formato, no período (sem o dia de hoje, que ainda não tem números maduros)."""
    start, end = (today - timedelta(days=days)).isoformat(), today.isoformat()
    out: dict[str, dict] = {}
    for row in (metrics.get("posts") or {}).values():
        t, day, sig = row.get("type"), row.get("date", ""), _signal(row)
        if not t or t == "compilation" or row.get("repost_of") or sig is None or not start <= day < end:
            continue
        p = out.setdefault(t, {"posts": 0, "total": 0, "first": day})
        p["posts"] += 1
        p["total"] += sig
        p["first"] = min(p["first"], day)
    for p in out.values():
        p["avg"] = round(p["total"] / p["posts"], 1)
    return out


def _bank_ok(kind: str, slots: list[dict], settings: dict, today: date) -> bool:
    """O banco do formato aguenta mais um horário por dia por pelo menos 30 dias?"""
    from . import saturation, state

    try:
        rows = saturation.status(today, state.load_used(), {**settings, "schedule": {"slots": slots}})
    except (OSError, ValueError):
        return True
    row = next((r for r in rows if r["kind"] == kind), None)
    return not row or row["days_left"] is None or row["days_left"] >= saturation.WARN_DAYS


def plan(metrics: dict, settings: dict, today: date, history: dict) -> dict:
    """{"change": {...}} com o ajuste a fazer, ou {"skip": motivo}."""
    cfg = settings_for(settings)
    if not cfg["enabled"]:
        return {"skip": "ajuste automático desligado (adapt.enabled)"}
    frozen = report.frozen_until(settings, today)
    if frozen:
        return {"skip": f"grade congelada até {frozen} (schedule.frozen_until)"}
    last = max((c.get("date", "") for c in history.get("changes", [])), default="")
    if last and last > (today - timedelta(days=int(cfg["cooldown_days"]))).isoformat():
        return {"skip": f"último ajuste em {last}; o próximo só depois de {cfg['cooldown_days']} dias"}
    slots = settings.get("schedule", {}).get("slots", [])
    days = int(cfg["zero_days"])
    perf = performance(metrics, today, days)
    # o formato precisa ter sido medido desde o começo das 2 semanas (com 2 dias de folga)
    span_start = (today - timedelta(days=days - 2)).isoformat()
    zero = [t for t, p in perf.items()
            if p["total"] == 0 and p["posts"] >= int(cfg["min_posts"]) and p["first"] <= span_start]
    if not zero:
        return {"skip": f"nenhum formato com alcance zero por {days} dias"}
    count = {t: sum(1 for s in slots if s["type"] == t) for t in perf}
    targets = sorted((t for t, p in perf.items() if p["avg"] > 0 and t != "verse"
                      and any(s["type"] == t for s in slots)), key=lambda t: perf[t]["avg"], reverse=True)
    for bad in sorted(zero, key=lambda t: count.get(t, 0), reverse=True):
        idx = [i for i, s in enumerate(slots) if s["type"] == bad and i > 0]
        if count.get(bad, 0) < 2 or not idx:
            continue  # fica com 1 horário (ou é o Versículo do primeiro horário)
        i = idx[-1]
        for good in targets:
            new_slots = copy.deepcopy(slots)
            new_slots[i]["type"] = good
            if not _bank_ok(good, new_slots, settings, today):
                continue
            reason = (f"{report.TYPE_NAME.get(bad, bad)} com alcance zero em {perf[bad]['posts']} posts "
                      f"nos últimos {days} dias; {report.TYPE_NAME.get(good, good)} alcança em média "
                      f"{perf[good]['avg']}")
            return {"change": {"date": today.isoformat(), "slot": i + 1, "time": slots[i]["time"],
                               "from": bad, "to": good, "reason": reason}, "slots": new_slots}
    names = ", ".join(report.TYPE_NAME.get(t, t) for t in zero)
    return {"skip": f"alcance zero em {names}, mas já está com 1 horário ou não há formato melhor para pôr no lugar"}


def apply(result: dict, settings: dict) -> None:
    settings = {**settings, "schedule": {**settings["schedule"], "slots": result["slots"]}}
    config.CONFIG_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    history = load_history()
    history.setdefault("changes", []).append(result["change"])
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    (config.STATE_DIR / HISTORY_FILE).write_text(json.dumps(history, ensure_ascii=False, indent=1) + "\n",
                                                 encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.adapt")
    parser.add_argument("--apply", action="store_true", help="grava o ajuste na agenda")
    parser.add_argument("--date")
    args = parser.parse_args(argv)
    path = config.STATE_DIR / "metrics.json"
    metrics = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    today = date.fromisoformat(args.date) if args.date else date.today()
    settings = config.load_settings()
    result = plan(metrics, settings, today, load_history())
    if not result.get("change"):
        print(f"Grade sem ajuste: {result['skip']}.")
        return 0
    c = result["change"]
    print(f"Ajuste: horário das {c['time']} passa de {c['from']} para {c['to']} ({c['reason']}).")
    if args.apply:
        apply(result, settings)
        print(f"Gravado em {config.CONFIG_PATH.relative_to(config.ROOT)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
