"""Gera os posts do dia (ou re-renderiza um post editado no painel).

Comandos:
  python -m app.generate run                 # gera e já salva no estado (uso local)
  python -m app.generate build --out p.json  # gera mídias + "patch" (usado no GitHub Actions)
  python -m app.generate apply p.json        # aplica o patch em state/
  python -m app.generate rerender --post-id ID --out p.json
  python -m app.generate compilation --out p.json    # vídeo longo de quiz (YouTube)
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

from . import captions, compilation, config, content, derived, music, publish, repost, state, validate
from .groq_client import GroqClient
from .render import cover
from .render import book as book_render
from .render import curiosity as curiosity_render
from .render import fill as fill_render
from .render import quiz as quiz_render
from .render import truefalse as truefalse_render
from .render import verse as verse_render

RENDERERS = {"verse": verse_render, "quiz": quiz_render, "curiosity": curiosity_render,
             "fill": fill_render, "truefalse": truefalse_render, "book": book_render}
CONTENT_FIELDS = {
    "verse": ["ref", "skip_prefix", "ref_label", "verse_text", "on_screen", "reflection", "theme",
              "mood", "tags", "application"],
    "quiz": ["ref", "ref_label", "question", "options", "answer", "evidence", "passage", "difficulty",
             "tags"],
    "curiosity": ["ref", "ref_label", "title", "text", "evidence", "passage", "tags"],
    "fill": ["ref", "ref_label", "verse_text", "question", "options", "answer", "answer_word", "tags"],
    "book": ["ref", "ref_label", "question", "options", "answer", "book_name", "tags"],
    "truefalse": ["ref", "ref_label", "question", "shown", "is_true", "correct", "evidence", "passage",
                  "difficulty"],
}
VIDEO_KINDS = ("quiz", "fill", "truefalse", "book")  # sempre em vídeo


def _today(settings: dict, override: str | None) -> date:
    if override:
        return date.fromisoformat(override)
    return datetime.now(ZoneInfo(settings.get("timezone", "America/Sao_Paulo"))).date()


def _seed(text: str) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16)


def _has_video(kind: str, settings: dict) -> bool:
    """O quiz sempre vira vídeo; Versículo e "Você sabia?" só se estiverem em video.video_types."""
    return kind in VIDEO_KINDS or kind in settings.get("video", {}).get("video_types", ["quiz"])


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
    if info.get("video_music"):
        # capa do YouTube com texto grande (o "poster" continua sendo um quadro do vídeo)
        cover.short_cover(kind, item, seed=_seed(post_id) + version,
                          handle=settings.get("brand", {}).get("handle", ""), out=out_dir / cover.SHORT_FILE)
        info["thumbnail"] = cover.SHORT_FILE
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

    patch = {"mode": "generate", "date": day, "posts": [], "used": {}}
    archived = {p["id"] for p in state.load_history()}
    taken = set(queue) | archived
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
        if post_id in archived:
            # já publicado em todas as redes e saiu da fila: refazer criaria uma cópia que
            # sobrescreve o original no histórico (e as métricas dele)
            print(f"{post_id}: já está no histórico, pulando")
            continue
        old = queue.get(post_id)
        if old and not args.force and not _replaceable(old):
            print(f"{post_id}: já existe, pulando (use --force para refazer)")
            continue
        if old:
            print(f"{post_id}: substituindo post {old.get('status')}")
        log: list[str] = []
        rng = random.Random(_seed(post_id))
        picker = derived.pick if kind in derived.KINDS else content.pick
        item, used_updates = picker(kind, today, used, groq, settings, rng, log)
        for section, values in used_updates.items():
            used.setdefault(section, {}).update(values)
            patch["used"].setdefault(section, {}).update(values)
        post = _make_post(kind, item, post_id, day, idx, slot["time"], old, settings, groq, media_root,
                          recent_tracks, rng, log, now)
        patch["posts"].append(post)
        print(f"{post_id}: ok ({item.get('source')}, legenda {post['caption_source']}, {post['media']['duration']}s)")
        for line in log:
            print(f"   · {line}")
    post = _compilation_post(settings, today, used, media_root, queue, taken, args.force or args.clear,
                             patch, len(settings["schedule"]["slots"]) + 1)
    if post:
        patch["posts"].append(post)
    post = _repost_post(settings, today, used, groq, media_root, queue, taken, args.force or args.clear,
                        patch, recent_tracks, len(settings["schedule"]["slots"]) + 2, now)
    if post:
        patch["posts"].append(post)
    patch["groq_usage"] = groq.usage
    return patch


def _make_post(kind: str, item: dict, post_id: str, day: str, idx: int, slot_time: str, old: dict | None,
               settings: dict, groq: GroqClient, media_root: Path, recent_tracks: list, rng: random.Random,
               log: list[str], now: datetime) -> dict:
    """Legendas, música, mídias e o registro do post para a fila."""
    tz = ZoneInfo(settings.get("timezone", "America/Sao_Paulo"))
    auto = settings.get("approval", {}).get("auto_approve", False)
    if kind == "verse" and config.verse_carousel(settings) and not item.get("application"):
        app_text = content.application(item, groq, log)
        if app_text:
            item = {**item, "application": app_text}
    caps, caption_source = captions.build(kind, item, settings, groq, rng, log)
    mood = music.MOOD_BY_TYPE.get(kind, item.get("mood", "reflexao"))
    track = None
    if _has_video(kind, settings):
        track = music.pick_track(mood, recent_tracks, rng)
        recent_tracks.append(track["id"])
    version = int((old or {}).get("media", {}).get("version", 0)) + 1  # novo ?v= evita cache
    media = _render(kind, item, post_id, day, settings, media_root, track, rng, version)

    status = "approved" if auto else "pending"
    when = publish.publish_at(post_id, day, slot_time, settings)
    if auto and datetime.fromisoformat(when).replace(tzinfo=tz) <= now:
        # horário já passou: não sai sozinho (evita publicar vários de uma vez);
        # use "Publicar agora" no painel se quiser
        status = "pending"
        log.append("horário já passou: aguardando você (aprovar ou Publicar agora)")
    return {
        "id": post_id,
        "date": day,
        "slot": idx,
        "time": slot_time,
        "publish_at": when,
        "type": kind,
        "status": status,
        "created_at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"),
        "source": item.get("source"),
        "bank_id": item.get("id") if item.get("source") == "bank" else None,
        "model": item.get("model"),
        "content": {k: item[k] for k in CONTENT_FIELDS[kind] if k in item},
        "captions": caps,
        "caption_source": caption_source,
        "hook": captions.hook_label(caps, caption_source),
        "music": {k: track.get(k, "") for k in ("id", "title", "source", "license", "url")}
                 if track else None,
        "gospel_suggestions": music.gospel_suggestions(mood, item.get("tags", []), rng),
        "media": media,
        "published": {p: None for p in state.PLATFORMS},
        "log": log,
        "error": None,
    }


def _repost_post(settings: dict, today: date, used: dict, groq: GroqClient, media_root: Path, queue: dict,
                 taken: set, redo: bool, patch: dict, recent_tracks: list, slot: int,
                 now: datetime) -> dict | None:
    """Domingo: o post com mais engajamento da semana volta em outro formato (app/repost.py).
    Se não houver candidato ou algo falhar, os posts do dia seguem normalmente."""
    cfg = repost.settings_of(settings)
    if not (cfg["enabled"] and today.weekday() == cfg["weekday"]):
        return None
    day = today.isoformat()
    prefix = f"{day}-{slot}-"
    if any(p["id"].startswith(prefix) for p in state.load_history()):
        print(f"repost de {day}: já existe, pulando")
        return None
    old = next((p for pid, p in queue.items() if pid.startswith(prefix)), None)
    if old and not ((redo and not any((old.get("published") or {}).values())) or _replaceable(old)):
        print(f"{old['id']}: já existe, pulando (use --force para refazer)")
        return None
    log: list[str] = []
    try:
        # refazendo: o post original do repost anterior pode ser escolhido de novo
        choice = repost.pick(today, settings, used, rng=random.Random(_seed(f"{day}|repost")), log=log,
                             allow=(old or {}).get("repost_of"))
        if not choice:
            print(f"repost de {day}: nenhum post da semana com engajamento para reaproveitar")
            for line in log:
                print(f"   · {line}")
            return None
        original, kind, item = choice
        post_id = old["id"] if old else f"{prefix}{kind}"
        n = 2
        while not old and post_id in taken:  # nunca reaproveita o ID de um post antigo
            post_id = f"{prefix}{kind}-v{n}"
            n += 1
        log.insert(0, f"repost do melhor post da semana ({original['id']}, {original['type']} → {kind})")
        post = _make_post(kind, item, post_id, day, slot, cfg["time"], old, settings, groq,
                          media_root, recent_tracks, random.Random(_seed(post_id)), log, now)
    except Exception as exc:  # noqa: BLE001 - nunca derruba a geração diária
        print(f"repost de {day}: NÃO gerado: {exc}")
        return None
    post.update({"source": "repost", "repost_of": original["id"], "bank_id": original.get("bank_id"),
                 "model": original.get("model")})
    updates = {"repost": {original["id"]: day}}
    for section, values in updates.items():
        used.setdefault(section, {}).update(values)
        patch["used"].setdefault(section, {}).update(values)
    print(f"{post_id}: ok (repost de {original['id']}, legenda {post['caption_source']})")
    for line in log:
        print(f"   · {line}")
    return post


def _compilation_post(settings: dict, today: date, used: dict, media_root: Path, queue: dict,
                      taken: set, redo: bool, patch: dict, slot: int, manual: bool = False) -> dict | None:
    """Vídeo longo de quiz (YouTube): uma vez por semana, no dia configurado. Se falhar, os
    posts do dia seguem normalmente."""
    comp = settings.get("compilation", {})
    if not manual and not (comp.get("enabled") and today.weekday() == int(comp.get("weekday", 6))):
        return None
    day = today.isoformat()
    post_id = f"{day}-{slot}-{compilation.KIND}"
    if manual:
        n = 2
        base = post_id
        while post_id in taken:
            post_id = f"{base}-v{n}"
            n += 1
    elif post_id in {p["id"] for p in state.load_history()} or (post_id in queue and not redo):
        print(f"{post_id}: já existe, pulando")
        return None
    log: list[str] = []
    try:
        post, updates = compilation.build_post(today, settings, used, media_root, post_id, slot, log)
    except Exception as exc:  # noqa: BLE001 - nunca derruba a geração diária
        print(f"{post_id}: vídeo longo NÃO gerado: {exc}")
        return None
    for section, values in updates.items():
        used.setdefault(section, {}).update(values)
        patch["used"].setdefault(section, {}).update(values)
    print(f"{post_id}: ok ({post['content']['count']} perguntas, {post['media']['duration']}s)")
    for line in log:
        print(f"   · {line}")
    return post


def build_compilation(args) -> dict:
    """Gera só o vídeo longo (botão do painel ou mode=compilation)."""
    settings = config.load_settings()
    today = _today(settings, args.date)
    used = state.load_used()
    taken = {p["id"] for p in state.load_queue()} | {p["id"] for p in state.load_history()}
    patch = {"mode": "generate", "date": today.isoformat(), "posts": [], "used": {}}
    post = _compilation_post(settings, today, used, Path(args.media_dir), {}, taken, True, patch,
                             len(settings["schedule"]["slots"]) + 1, manual=True)
    if not post:
        raise SystemExit("Não foi possível gerar o vídeo longo (veja o log acima).")
    patch["posts"].append(post)
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


VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v"}


def prune_media(media_root: Path, today: date, keep_days: int) -> None:
    """Apaga as mídias de dias com mais de keep_days. Dos posts que já saíram da fila
    (publicados, rejeitados na limpeza etc.) apaga só os vídeos, que são o que pesa: as
    imagens ficam pelos keep_days para o Histórico e as páginas do mini-site (prévia no WhatsApp)."""
    limit = (today - timedelta(days=keep_days)).isoformat()
    if not media_root.exists():
        return
    in_queue = {p["id"] for p in state.load_queue()}
    for day_dir in media_root.iterdir():
        if not day_dir.is_dir():
            continue
        if day_dir.name < limit:
            shutil.rmtree(day_dir)
            print(f"mídia antiga removida: {day_dir.name}")
            continue
        for post_dir in day_dir.iterdir():
            if not post_dir.is_dir() or post_dir.name in in_queue:
                continue
            videos = [f for f in post_dir.iterdir() if f.suffix.lower() in VIDEO_SUFFIXES]
            for f in videos:
                f.unlink()
            if videos:
                print(f"vídeos removidos (post fora da fila): {post_dir.name}")
            if not any(post_dir.iterdir()):
                post_dir.rmdir()
        if not any(day_dir.iterdir()):
            day_dir.rmdir()


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
    p = sub.add_parser("compilation", help="gera só o vídeo longo de quiz (YouTube)")
    p.add_argument("--date")
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
    # a fila do painel mostra só os posts de hoje; dias anteriores vão para o Histórico
    queue_keep = int(settings.get("queue_keep_days", 0))
    if args.cmd in ("run", "build", "rerender", "compilation"):
        patch = {"run": build, "build": build, "rerender": rerender, "compilation": build_compilation}[args.cmd](args)
        Path(args.out).write_text(json.dumps(patch, ensure_ascii=False, indent=1), encoding="utf-8")
        if args.cmd == "run":
            state.apply_patch(patch, _today(settings, args.date), queue_keep)
            prune_media(Path(args.media_dir), _today(settings, args.date), keep)
            print("estado atualizado em state/")
    elif args.cmd == "apply":
        patch = json.loads(Path(args.patch).read_text(encoding="utf-8"))
        state.apply_patch(patch, _today(settings, args.date), queue_keep)
        print(f"patch aplicado ({len(patch.get('posts', []))} post(s))")
    elif args.cmd == "prune-media":
        prune_media(Path(args.media_dir), _today(settings, args.date), keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
