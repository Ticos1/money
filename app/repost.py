"""Repost semanal: o post com mais engajamento da semana volta no domingo, em outro formato.

Conteúdo que já funcionou tende a render de novo, e quem começou a seguir nesta
semana não viu. Para não parecer repetido, ele volta em outro formato:

  Desafio de quiz      → Verdadeiro ou falso (mesma pergunta, com uma resposta mostrada)
  Verdadeiro ou falso  → Desafio de quiz (a pergunta original, com as 4 alternativas)
  Versículo do dia     → Complete o versículo
  Complete o versículo → Versículo do dia (com reflexão e carrossel)

Engajamento = a mesma conta do resumo semanal (app/report.py): curtidas + 2×comentários
+ 3×salvamentos e compartilhamentos, somando Instagram, Facebook e YouTube. Em empate,
ganha o de maior alcance. O mesmo post nunca é reaproveitado duas vezes, e um repost
nunca vira repost de novo.

Configuração em config/settings.json:
  "repost": {"enabled": true, "weekday": 6, "time": "19:15", "days": 7}
  (weekday: 0 = segunda … 6 = domingo; days: quantos dias para trás olhar)
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta

from . import bible, config, derived, report, state, validate

CONVERT = {"quiz": "truefalse", "truefalse": "quiz", "verse": "fill", "fill": "verse"}
DEFAULTS = {"enabled": True, "weekday": 6, "time": "19:15", "days": 7}


def settings_of(settings: dict) -> dict:
    cfg = {**DEFAULTS, **(settings.get("repost") or {})}
    return {"enabled": bool(cfg["enabled"]), "weekday": int(cfg["weekday"]), "time": str(cfg["time"]),
            "days": max(1, int(cfg["days"]))}


def _load_metrics() -> dict:
    path = config.STATE_DIR / "metrics.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _bank_item(kind: str, bank_id: str | None) -> dict | None:
    if not bank_id:
        return None
    raw = next((i for i in validate.load_bank(kind) if i.get("id") == bank_id), None)
    return validate.validate(kind, dict(raw)) if raw else None


def convert(post: dict, rng: random.Random) -> tuple[str, dict] | None:
    """(novo formato, conteúdo validado na Bíblia) ou None se este post não tem outro formato."""
    src = post.get("type")
    content = dict(post.get("content") or {})
    try:
        if src == "quiz":
            return "truefalse", derived.make_truefalse(validate.validate("quiz", content), rng)
        if src == "truefalse":
            item = _bank_item("quiz", post.get("bank_id"))
            return ("quiz", item) if item else None
        if src == "verse":
            item = derived.make_fill(validate.validate("verse", content), rng)
            return ("fill", item) if item else None
        if src == "fill":
            item = _bank_item("verse", post.get("bank_id"))
            return ("verse", item) if item else None
    except (validate.ContentError, bible.BibleError, KeyError, TypeError, ValueError):
        return None
    return None


def ranked(metrics: dict, today: date, days: int) -> list[tuple[str, int, int]]:
    """[(id do post, engajamento, alcance)] da semana, do melhor para o pior (só engajamento > 0)."""
    start = (today - timedelta(days=days)).isoformat()
    out = []
    for pid, row in (metrics.get("posts") or {}).items():
        if not start <= str(row.get("date", "")) < today.isoformat():
            continue
        if row.get("type") not in CONVERT or row.get("repost_of"):
            continue
        score = report.engagement(row)
        if score > 0:
            out.append((pid, score, report.reach(row) or 0))
    return sorted(out, key=lambda x: (x[1], x[2], x[0]), reverse=True)


def pick(today: date, settings: dict, used: dict, rng: random.Random, log: list[str],
         metrics: dict | None = None, allow: str | None = None) -> tuple[dict, str, dict] | None:
    """(post original, novo formato, conteúdo) do melhor post da semana que ainda não foi
    reaproveitado. `allow`: id que pode ser escolhido mesmo já marcado (refazer o repost)."""
    cfg = settings_of(settings)
    metrics = _load_metrics() if metrics is None else metrics
    done = {k for k in (used.get("repost") or {}) if k != allow}
    posts = {p["id"]: p for p in state.load_history() + state.load_queue()}
    for pid, score, _ in ranked(metrics, today, cfg["days"]):
        original = posts.get(pid)
        if pid in done or not original or original.get("repost_of"):
            continue
        converted = convert(original, rng)
        if not converted:
            log.append(f"repost: {pid} ({score} de engajamento) não tem outro formato, tentando o próximo")
            continue
        kind, item = converted
        return original, kind, item
    return None
