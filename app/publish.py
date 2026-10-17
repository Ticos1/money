"""Publica nas redes os posts APROVADOS cujo horário já chegou.

  python -m app.publish --media-dir media_repo/media --out patch.json

Roda de hora em hora pelo GitHub Actions e logo depois de você aprovar um post
no painel. Cada rede só é tentada se estiver ligada em config/settings.json
(publishing) e se as chaves dela existirem nos Secrets. Se der erro, tenta de
novo nas próximas execuções (até publishing.max_attempts vezes) e o painel
mostra o motivo.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, state
from .publishers import PublishError

MEDIA_URL_TTL = 3 * 3600  # links temporários valem 3 horas
JITTER_MINUTES = 10  # padrão de publishing.time_jitter_minutes


def publish_at(post_id: str, day: str, slot_time: str, settings: dict) -> str:
    """Horário real de publicação: o do slot ± até N minutos (publishing.time_jitter_minutes),
    para os posts não saírem sempre no minuto exato e não parecerem automação.
    Sorteio fixo por post (refazer o post mantém o horário). Formato "AAAA-MM-DDTHH:MM", fuso local."""
    minutes = max(0, int(settings.get("publishing", {}).get("time_jitter_minutes", JITTER_MINUTES)))
    offset = random.Random(f"{post_id}|horario").randint(-minutes, minutes)
    when = datetime.fromisoformat(f"{day}T{slot_time}") + timedelta(minutes=offset)
    return when.strftime("%Y-%m-%dT%H:%M")


def scheduled_at(post: dict, tz: ZoneInfo) -> datetime:
    """Quando o post deve sair (posts antigos, sem publish_at, usam o horário do slot)."""
    local = post.get("publish_at") or f"{post['date']}T{post.get('time', '00:00')}"
    return datetime.fromisoformat(local).replace(tzinfo=tz)


def sign_media_path(path: str, exp: int, secret: str) -> str:
    """Mesma assinatura conferida pelo painel (dashboard/functions/_middleware.js)."""
    return hmac.new(secret.encode(), f"{path}|{exp}".encode(), hashlib.sha256).hexdigest()


def media_url_factory(post: dict):
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    secret = os.environ.get("MEDIA_SIGNING_SECRET", "")

    def media_url(filename: str) -> str:
        if not base or len(secret) < 32:
            raise PublishError("configure PUBLIC_BASE_URL e MEDIA_SIGNING_SECRET (32+ caracteres)")
        path = f"/{post['media']['base']}{filename}"
        exp = int(time.time()) + MEDIA_URL_TTL
        return f"{base}{path}?v={post['media'].get('version', 1)}&exp={exp}&sig={sign_media_path(path, exp, secret)}"

    return media_url


def is_due(post: dict, now: datetime, tz: ZoneInfo) -> bool:
    if post.get("status") != "approved" or not post.get("media", {}).get("base"):
        return False
    return scheduled_at(post, tz) <= now


def applies(platform: str, post: dict, cfg: dict | None = None) -> bool:
    """A rede aceita este post? (YouTube/TikTok só vídeo; "<rede>_types" nas configurações,
    ex.: youtube_types ou facebook_types, limita a rede aos tipos escolhidos, e "<rede>_times",
    ex.: instagram_times, aos horários da grade escolhidos.)"""
    media = post.get("media", {})
    only = (cfg or {}).get(f"{platform}_types")
    if isinstance(only, list) and post.get("type") not in only:
        return False
    if post.get("type") == "compilation":  # vídeo longo 16:9: só YouTube, fora da grade de horários
        return platform == "youtube" and bool(media.get("video_music"))
    times = (cfg or {}).get(f"{platform}_times")
    if isinstance(times, list) and post.get("time") not in times:
        return False
    if platform == "youtube":
        return bool(media.get("video_music"))
    if platform == "tiktok":
        return bool(media.get("video_silent"))
    if platform == "stories":
        return bool(media.get("video_music") or "imagem_story.jpg" in media.get("images", []))
    return True


def completed_posts(posts: list[dict], cfg: dict, results: dict) -> list[str]:
    """Posts que já saíram em TODAS as redes ligadas (ou foram pulados de propósito, como no
    limite diário do YouTube): saem da fila e vão pro Histórico."""
    done = []
    for post in posts:
        published = {**(post.get("published") or {}), **(post.get("publish_skipped") or {}),
                     **{k: v.get("at") or v.get("skipped")
                        for k, v in results.get(post["id"], {}).items() if v.get("at") or v.get("skipped")}}
        nets = [p for p in state.PLATFORMS if cfg.get(p) and applies(p, post, cfg)]
        if nets and all(published.get(p) for p in nets):
            done.append(post["id"])
    return done


def uploads_today(posts: list[dict], now: datetime, tz: ZoneInfo, platform: str = "youtube") -> int:
    """Quantos posts já saíram hoje (dia de Brasília) na rede."""
    today = now.date()
    count = 0
    for p in posts:
        at = (p.get("published") or {}).get(platform)
        if not at:
            continue
        try:
            when = datetime.fromisoformat(at)
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=ZoneInfo("UTC"))
        if when.astimezone(tz).date() == today:
            count += 1
    return count


def build_publishers(enabled: dict, log: list[str]) -> tuple[dict, dict]:
    """Devolve (publicadores prontos, erros de configuração por rede)."""
    pubs, errors = {}, {}
    env = os.environ.get
    if enabled.get("instagram") or enabled.get("facebook") or enabled.get("stories"):
        if env("META_ACCESS_TOKEN"):
            try:
                from .publishers.meta import FacebookPublisher, InstagramPublisher, MetaAccount
                acc = MetaAccount(env("META_ACCESS_TOKEN"), env("META_PAGE_ID") or None)
                if enabled.get("facebook"):
                    pubs["facebook"] = FacebookPublisher(acc)
                if enabled.get("instagram"):
                    try:
                        pubs["instagram"] = InstagramPublisher(acc)
                    except PublishError as exc:
                        errors["instagram"] = str(exc)
                if enabled.get("stories"):
                    try:
                        from .publishers.meta import InstagramStoryPublisher
                        pubs["stories"] = InstagramStoryPublisher(acc)
                    except PublishError as exc:
                        errors["stories"] = str(exc)
            except PublishError as exc:
                for p in ("instagram", "facebook", "stories"):
                    if enabled.get(p):
                        errors[p] = str(exc)
        else:
            log.append("Instagram/Facebook/Stories ligados, mas falta o segredo META_ACCESS_TOKEN")
    if enabled.get("tiktok"):
        if env("TIKTOK_CLIENT_KEY") and env("TIKTOK_CLIENT_SECRET") and env("MEDIA_SIGNING_SECRET"):
            try:
                from .publishers.tiktok import TikTokPublisher
                pubs["tiktok"] = TikTokPublisher(state.load_tiktok_auth(), env("TIKTOK_CLIENT_KEY"),
                                                 env("TIKTOK_CLIENT_SECRET"), env("MEDIA_SIGNING_SECRET"))
            except PublishError as exc:
                errors["tiktok"] = str(exc)
        else:
            log.append("TikTok ligado, mas faltam TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET / MEDIA_SIGNING_SECRET")
    if enabled.get("youtube"):
        if env("YT_REFRESH_TOKEN") and env("YT_CLIENT_ID") and env("YT_CLIENT_SECRET"):
            try:
                from .publishers.youtube import YouTubePublisher
                pubs["youtube"] = YouTubePublisher(env("YT_CLIENT_ID"), env("YT_CLIENT_SECRET"),
                                                   env("YT_REFRESH_TOKEN"))
            except PublishError as exc:
                errors["youtube"] = str(exc)
        else:
            log.append("YouTube ligado, mas faltam YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN")
    return pubs, errors


def run(media_dir: Path, only_post: str | None = None, only_platform: str | None = None,
        now_ignore_time: bool = False) -> dict:
    settings = config.load_settings()
    cfg = settings.get("publishing", {})
    enabled = {p: bool(cfg.get(p)) and (not only_platform or p == only_platform) for p in state.PLATFORMS}
    max_attempts = int(cfg.get("max_attempts", 3))
    tz = ZoneInfo(settings.get("timezone", "America/Sao_Paulo"))
    now = datetime.now(tz)
    log: list[str] = []

    # "agora" (teste manual) ignora o horário, mas só vale para um post específico
    check_time = not (now_ignore_time and only_post)
    due = [p for p in state.load_queue()
           if (not only_post or p["id"] == only_post)
           and (is_due(p, now, tz) if check_time else p.get("status") == "approved")]
    pending = []
    for post in due:
        for platform, on in enabled.items():
            if not on or (post.get("published") or {}).get(platform) \
                    or (post.get("publish_skipped") or {}).get(platform) \
                    or not applies(platform, post, cfg):
                continue
            attempts = ((post.get("publish_errors") or {}).get(platform) or {}).get("attempts", 0)
            if attempts >= max_attempts:
                continue
            pending.append((post, platform))
    results: dict[str, dict] = {}
    if not pending:
        print("Nada para publicar agora.")
        return {"mode": "publish", "publish_results": results,
                "completed": completed_posts(due, cfg, results)}

    pubs, config_errors = build_publishers(enabled, log)
    for line in log:
        print("·", line)
    # limite por dia em cada rede ("<rede>_max_per_day"). YouTube: a cota grátis da API dá 5 envios
    # (cada Short gasta 1.700 de 10.000 pontos: envio 1.600 + capa 50 + comentário 50)
    caps = {p: int(cfg[f"{p}_max_per_day"]) for p in state.PLATFORMS if f"{p}_max_per_day" in cfg}
    caps.setdefault("youtube", 5)
    posted = state.load_queue() + state.load_history()
    used = {p: uploads_today(posted, now, tz, p) for p in caps}
    for post, platform in pending:
        out = results.setdefault(post["id"], {})
        if platform in caps and used[platform] >= caps[platform]:
            out[platform] = {"skipped": f"pulado: limite de {caps[platform]} vídeos por dia no YouTube (cota da API)"
                             if platform == "youtube" else f"pulado: limite de {caps[platform]} posts por dia no {platform}"}
            print(f"{post['id']} → {platform}: {out[platform]['skipped']}")
            continue
        if platform in config_errors:
            out[platform] = {"error": config_errors[platform]}
            print(f"{post['id']} → {platform}: ERRO {config_errors[platform]}")
            continue
        pub = pubs.get(platform)
        if not pub or not pub.supports(post):
            continue
        try:
            url = pub.publish(post, media_dir / post["date"] / post["id"], media_url_factory(post))
            out[platform] = {"at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"), "url": url}
            if platform in used:
                used[platform] += 1
            print(f"{post['id']} → {platform}: publicado {url}")
        except PublishError as exc:
            out[platform] = {"error": str(exc)[:500]}
            print(f"{post['id']} → {platform}: ERRO {exc}")
    patch = {"mode": "publish", "publish_results": results, "completed": completed_posts(due, cfg, results)}
    if getattr(pubs.get("tiktok"), "updated_auth", None):
        patch["tiktok_auth"] = pubs["tiktok"].updated_auth  # token renovado (criptografado)
    return patch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.publish")
    parser.add_argument("--media-dir", default="media")
    parser.add_argument("--out", default="patch.json")
    parser.add_argument("--post-id")
    parser.add_argument("--platform", help="publicar só nesta rede")
    parser.add_argument("--now", action="store_true", help="ignorar o horário (exige --post-id)")
    args = parser.parse_args(argv)
    patch = run(Path(args.media_dir), args.post_id or None, args.platform or None, args.now)
    Path(args.out).write_text(json.dumps(patch, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
