"""Estado do sistema guardado em arquivos JSON na pasta state/ (versionados no Git).

- queue.json    posts recentes (fila do painel), com status e onde já foi publicado
- history.json  posts antigos arquivados (saem da fila após N dias)
- used.json     conteúdos já usados, para nunca repetir
- groq.json     contador diário de chamadas à Groq (respeita o plano grátis)
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .config import STATE_DIR

PLATFORMS = ("tiktok", "kwai", "youtube", "instagram", "facebook")


def _read(name: str, default):
    path = STATE_DIR / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write(name: str, data) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / name).write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def load_queue() -> list[dict]:
    return _read("queue.json", {"posts": []})["posts"]


def save_queue(posts: list[dict]) -> None:
    posts = sorted(posts, key=lambda p: (p["date"], p["slot"]), reverse=True)
    _write("queue.json", {"posts": posts})


def load_history() -> list[dict]:
    return _read("history.json", {"posts": []})["posts"]


def save_history(posts: list[dict]) -> None:
    _write("history.json", {"posts": posts})


def load_used() -> dict:
    return _read("used.json", {"verse": {}, "quiz": {}, "curiosity": {}, "refs": {}, "fingerprints": {}})


def save_used(used: dict) -> None:
    _write("used.json", used)


def load_groq_usage() -> dict:
    return _read("groq.json", {"date": "", "calls": 0})


def save_groq_usage(usage: dict) -> None:
    _write("groq.json", usage)


def archive_old(posts: list[dict], today: date, keep_days: int) -> tuple[list[dict], list[dict]]:
    """Separa (fila, arquivados): posts com mais de keep_days dias saem da fila."""
    limit = (today - timedelta(days=keep_days)).isoformat()
    keep = [p for p in posts if p["date"] >= limit]
    old = [p for p in posts if p["date"] < limit]
    return keep, old


def apply_patch(patch: dict, today: date, keep_days: int) -> None:
    """Aplica o resultado da geração nos arquivos de estado.

    É idempotente (upsert por id) para poder ser repetido com segurança se o
    push para o GitHub falhar e precisarmos reaplicar sobre a versão mais nova.
    """
    posts = {p["id"]: p for p in load_queue()}
    for new in patch.get("posts", []):
        old = posts.get(new["id"])
        if old:
            # preserva o que o usuário fez no painel (status/publicações)
            new = {**new, "published": {**new.get("published", {}), **old.get("published", {})}}
            if patch.get("mode") == "rerender":
                new["status"] = old.get("status", new["status"])
                new["captions"] = old.get("captions", new["captions"])
        posts[new["id"]] = new
    queue, archived = archive_old(list(posts.values()), today, keep_days)
    save_queue(queue)
    if archived:
        history = {p["id"]: p for p in load_history()}
        for p in archived:
            p.pop("media", None)  # mídias antigas são apagadas para economizar espaço
            history[p["id"]] = p
        save_history(sorted(history.values(), key=lambda p: (p["date"], p["slot"]), reverse=True))

    used = load_used()
    for section, values in patch.get("used", {}).items():
        used.setdefault(section, {}).update(values)
    save_used(used)

    if "groq_usage" in patch:
        current = load_groq_usage()
        incoming = patch["groq_usage"]
        if current.get("date") == incoming["date"]:
            incoming = {**incoming, "calls": max(current.get("calls", 0), incoming["calls"])}
        save_groq_usage(incoming)
