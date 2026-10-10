"""Gera os posts do dia (ou re-renderiza um post editado no painel).

Comandos:
  python -m app.generate run                 # gera e já salva no estado (uso local)
  python -m app.generate build --out p.json  # gera mídias + "patch" (usado no GitHub Actions)
  python -m app.generate apply p.json        # aplica o patch em state/
  python -m app.generate rerender --post-id ID --out p.json
  python -m app.generate prune-media --media-dir media

Opções úteis: --date 2026-10-09  --force (refaz posts do dia)  --no-groq
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import captions, config, content, music, state, validate
from .groq_client import GroqClient
from .render import curiosity as curiosity_render
from .render import quiz as quiz_render
from .render import verse as verse_render

RENDERERS = {"verse": verse_render, "quiz": quiz_render, "curiosity": curiosity_render}
CONTENT_FIELDS = {
    "verse": ["ref", "skip_prefix", "ref_label", "verse_text", "on_screen", "reflection", "theme",
              "mood", "tags"],
    "quiz": ["ref", "ref_label", "question", "options", "answer", "evidence", "passage", "difficulty",
             "tags"],
    "curiosity": ["ref", "ref_label", "title", "text", "evidence", "passage", "tags"],
}


def _today(settings: dict, override: str | None) -> date:
    if override:
        return date.fromisoformat(override)
    return datetime.now(ZoneInfo(settings.get("timezone", "America/Sao_Paulo"))).date()


def _seed(text: str) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16)


def _has_video(kind: str, settings: dict) -> bool:
    return kind == "quiz" or verse_render.wants_video(settings)


def _replaceable(post: dict) -> bool:
    """Post rejeitado e ainda não publicado em nenhuma rede pode ser refeito."""
    return post.get("status") == "rejected" and not any((post.get("published") or {}).values())


def _render(kind: str, item: dict, post_id: str, day: str, settings: dict, media_root: Path,
            track: dict | None, rng: random.Random, version: int) -> dict:
    out_dir = media_root / day / post_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as work:
        info = RENDERERS[kind].render(item, settings, out_dir, _seed(post_id) + version,
                                      config.MUSIC_DIR / track["file"] if track else None, rng,
                                      Path(work))
    return {**info, "base": f"media/{day}/{post_id}/", "version": version}


def build(args) -> dict:
    settings = config.load_settings()
    today = _today(settings, args.date)
    day = today.isoformat()
    queue = {p["id"]: p for p in state.load_queue()}
    used = state.load_used()
    groq = GroqClient(None if args.no_groq else config.groq_api_key(), settings,
                      state.load_groq_usage(), today)
    media_root = Path(args.media_dir)
    recent_tracks = [(p.get("music") or {}).get("id") for p in sorted(queue.values(), key=lambda p: p["id"])]
    auto = settings.get("approval", {}).get("auto_approve", False)

    patch = {"mode": "generate", "date": day, "posts": [], "used": {}}
    taken = set(queue) | {p["id"] for p in state.load_history()}
    if args.clear:
        # "Gerar agora" com limpeza: a fila atual vai para o histórico e o dia é refeito do zero
        patch["clear_queue"] = True
        queue = {}
    tz = ZoneInfo(settings.get("timezone", "America/Sao_Paulo"))
    now = datetime.now(tz)
    for idx, slot in enumerate(settings["schedule"]["slots"], start=1):
        kind = slot["type"]
        post_id = f"{day}-{idx}-{kind}"
        if args.clear:
            n = 2
            while post_id in taken:  # nunca reaproveita o ID de um post antigo
                post_id = f"{day}-{idx}-{kind}-v{n}"
                n += 1
        old = queue.get(post_id)
        if old and not args.force and not _replaceable(old):
            print(f"{post_id}: já existe, pulando (use --force para refazer)")
            continue
        if old:
            print(f"{post_id}: substituindo post {old.get('status')}")
        log: list[str] = []
        rng = random.Random(_seed(post_id))
        item, used_updates = content.pick(kind, today, used, groq, settings, rng, log)
        for section, values in used_updates.items():
            used.setdefault(section, {}).update(values)
            patch["used"].setdefault(section, {}).update(values)

        caps, caption_source = captions.build(kind, item, settings, groq, rng, log)
        mood = music.MOOD_BY_TYPE.get(kind, item.get("mood", "reflexao"))
        track = None
        if _has_video(kind, settings):
            track = music.pick_track(mood, recent_tracks, rng)
            recent_tracks.append(track["id"])
        version = int((old or {}).get("media", {}).get("version", 0)) + 1  # novo ?v= evita cache
        media = _render(kind, item, post_id, day, settings, media_root, track, rng, version)

        status = "approved" if auto else "pending"
        slot_time = datetime.fromisoformat(f"{day}T{slot['time']}").replace(tzinfo=tz)
        if auto and slot_time <= now:
            # horário já passou: não sai sozinho (evita publicar vários de uma vez);
            # use "Publicar agora" no painel se quiser
            status = "pending"
            log.append("horário já passou: aguardando você (aprovar ou Publicar agora)")
        post = {
            "id": post_id,
            "date": day,
            "slot": idx,
            "time": slot["time"],
            "type": kind,
            "status": status,
            "created_at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"),
            "source": item.get("source"),
            "bank_id": item.get("id") if item.get("source") == "bank" else None,
            "model": item.get("model"),
            "content": {k: item[k] for k in CONTENT_FIELDS[kind] if k in item},
            "captions": caps,
            "caption_source": caption_source,
            "music": {k: track.get(k, "") for k in ("id", "title", "source", "license", "url")}
                     if track else None,
            "gospel_suggestions": music.gospel_suggestions(mood, item.get("tags", []), rng),
            "media": media,
            "published": {p: None for p in state.PLATFORMS},
            "log": log,
            "error": None,
        }
        patch["posts"].append(post)
        print(f"{post_id}: ok ({item.get('source')}, legenda {caption_source}, {media['duration']}s)")
        for line in log:
            print(f"   · {line}")
    patch["groq_usage"] = groq.usage
    return patch


def rerender(args) -> dict:
    settings = config.load_settings()
    posts = {p["id"]: p for p in state.load_queue()}
    post = posts.get(args.post_id)
    if not post:
        raise SystemExit(f"Post {args.post_id} não encontrado na fila")
    kind = post["type"]
    patch = {"mode": "rerender", "posts": []}
    try:
        item = validate.validate(kind, dict(post["content"]))
    except validate.ContentError as exc:
        post = {**post, "error": f"Edição inválida: {exc}", "needs_render": False}
        patch["posts"].append(post)
        print(post["error"])
        return patch
    track = next((t for t in music.load_library()
                  if t["id"] == (post.get("music") or {}).get("id")), None)
    if not _has_video(kind, settings):
        track = None
    elif not track:
        track = music.pick_track(music.MOOD_BY_TYPE.get(kind, item.get("mood", "reflexao")), [],
                                 random.Random(0))
    version = int(post.get("media", {}).get("version", 1)) + 1
    rng = random.Random(_seed(post["id"]) + version)
    media = _render(kind, item, post["id"], post["date"], settings, Path(args.media_dir), track, rng,
                    version)
    post = {**post, "content": {k: item[k] for k in CONTENT_FIELDS[kind] if k in item},
            "media": media, "error": None, "needs_render": False,
            "music": {k: track.get(k, "") for k in ("id", "title", "source", "license", "url")}
                     if track else None}
    patch["posts"].append(post)
    print(f"{post['id']}: re-renderizado (versão {version})")
    return patch


def prune_media(media_root: Path, today: date, keep_days: int) -> None:
    limit = (today - timedelta(days=keep_days)).isoformat()
    if not media_root.exists():
        return
    for day_dir in media_root.iterdir():
        if day_dir.is_dir() and day_dir.name < limit:
            shutil.rmtree(day_dir)
            print(f"mídia antiga removida: {day_dir.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.generate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("run", "build"):
        p = sub.add_parser(name)
        p.add_argument("--date")
        p.add_argument("--force", action="store_true")
        p.add_argument("--clear", action="store_true", help="tira a fila atual e refaz o dia")
        p.add_argument("--no-groq", action="store_true")
        p.add_argument("--media-dir", default="media")
        p.add_argument("--out", default="patch.json")
    p = sub.add_parser("rerender")
    p.add_argument("--post-id", required=True)
    p.add_argument("--media-dir", default="media")
    p.add_argument("--out", default="patch.json")
    p = sub.add_parser("apply")
    p.add_argument("patch")
    p.add_argument("--date")
    p = sub.add_parser("prune-media")
    p.add_argument("--media-dir", default="media")
    p.add_argument("--date")
    args = parser.parse_args(argv)

    settings = config.load_settings()
    keep = int(settings.get("media_retention_days", 30))
    if args.cmd in ("run", "build", "rerender"):
        patch = build(args) if args.cmd != "rerender" else rerender(args)
        Path(args.out).write_text(json.dumps(patch, ensure_ascii=False, indent=1), encoding="utf-8")
        if args.cmd == "run":
            state.apply_patch(patch, _today(settings, args.date), keep)
            prune_media(Path(args.media_dir), _today(settings, args.date), keep)
            print("estado atualizado em state/")
    elif args.cmd == "apply":
        patch = json.loads(Path(args.patch).read_text(encoding="utf-8"))
        state.apply_patch(patch, _today(settings, args.date), keep)
        print(f"patch aplicado ({len(patch.get('posts', []))} post(s))")
    elif args.cmd == "prune-media":
        prune_media(Path(args.media_dir), _today(settings, args.date), keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
