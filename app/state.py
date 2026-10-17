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

PLATFORMS = ("tiktok", "kwai", "youtube", "instagram", "facebook", "stories", "whatsapp")
# stories = Stories do Instagram · whatsapp = canal do WhatsApp (manual, pelo painel)


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


def load_tiktok_auth() -> dict:
    return _read("tiktok.json", {})


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


def _was_published(post: dict) -> bool:
    return any((post.get("published") or {}).values())


def apply_patch(patch: dict, today: date, keep_days: int) -> None:
    """Aplica o resultado da geração nos arquivos de estado.

    É idempotente (upsert por id) para poder ser repetido com segurança se o
    push para o GitHub falhar e precisarmos reaplicar sobre a versão mais nova.
    """
    posts = {p["id"]: p for p in load_queue()}
    cleared: list[dict] = []
    if patch.get("clear_queue"):
        new_ids = {p["id"] for p in patch.get("posts", [])}
        cleared = [p for pid, p in posts.items() if pid not in new_ids]
        posts = {pid: p for pid, p in posts.items() if pid in new_ids}
    for new in patch.get("posts", []):
        old = posts.get(new["id"])
        if old:
            # preserva o que o usuário fez no painel (status/publicações)
            new = {**new, "published": {**new.get("published", {}), **old.get("published", {})}}
            if patch.get("mode") == "rerender":
                new["status"] = old.get("status", new["status"])
                new["captions"] = old.get("captions", new["captions"])
        posts[new["id"]] = new
    for post_id, by_platform in patch.get("publish_results", {}).items():
        post = posts.get(post_id)
        if not post:
            continue
        post.pop("publishing_now", None)  # o "Publicar agora" terminou
        for platform, res in by_platform.items():
            errors = post.setdefault("publish_errors", {})
            if res.get("at"):
                post.setdefault("published", {})[platform] = res["at"]
                post.setdefault("publish_links", {})[platform] = res.get("url", "")
                errors.pop(platform, None)
            elif res.get("skipped"):  # pulado de propósito (ex.: limite diário do YouTube)
                post.setdefault("publish_skipped", {})[platform] = res["skipped"]
                errors.pop(platform, None)
            elif res.get("error"):
                prev = errors.get(platform) or {}
                errors[platform] = {"message": res["error"], "attempts": prev.get("attempts", 0) + 1}
    for post_id in patch.get("completed", []):  # já saiu em todas as redes
        if post_id in posts:
            cleared.append(posts.pop(post_id))
    queue, archived = archive_old(list(posts.values()), today, keep_days)
    archived += cleared
    save_queue(queue)
    if archived:
        history = {p["id"]: p for p in load_history()}
        for p in archived:
            p.pop("media", None)  # mídias antigas são apagadas para economizar espaço
            prev = history.get(p["id"])
            if prev and _was_published(prev) and not _was_published(p):
                continue  # uma cópia não publicada nunca apaga o registro do post que saiu nas redes
            if p.get("status") == "pending" and not _was_published(p):
                continue  # nunca aprovado nem publicado: não vale guardar (só enchia o histórico)
            history[p["id"]] = p
        save_history(sorted(history.values(), key=lambda p: (p["date"], p["slot"]), reverse=True))

    used = load_used()
    for section, values in patch.get("used", {}).items():
        used.setdefault(section, {}).update(values)
    save_used(used)

    if patch.get("tiktok_auth"):
        current = load_tiktok_auth()
        # só grava se ninguém reconectou a conta no meio tempo
        if current.get("open_id") in (None, patch["tiktok_auth"].get("open_id")):
            _write("tiktok.json", patch["tiktok_auth"])

    if "groq_usage" in patch:
        current = load_groq_usage()
        incoming = patch["groq_usage"]
        if current.get("date") == incoming["date"]:
            incoming = {**incoming, "calls": max(current.get("calls", 0), incoming["calls"])}
        save_groq_usage(incoming)
