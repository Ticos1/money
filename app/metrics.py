"""Coleta métricas dos posts publicados (Instagram, Facebook e YouTube).

  python -m app.metrics --out metrics.json

Roda junto da publicação (GitHub Actions) e grava state/metrics.json, que o
painel mostra na aba "Métricas". Tudo pelas APIs oficiais e com os mesmos
tokens já configurados. Se faltar alguma permissão (ex.: alcance/salvamentos do
Instagram precisam de instagram_manage_insights; visualizações e tempo médio dos
vídeos do Facebook precisam de read_insights; tempo assistido do YouTube precisa do escopo
yt-analytics.readonly), coleta o que der e avisa.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import captions, state
from .publishers import PublishError

KEEP_DAYS = 60
IG_INSIGHTS = {
    "REELS": "reach,saved,shares,views,total_interactions,ig_reels_avg_watch_time,ig_reels_video_view_total_time",
    "FEED": "reach,saved,shares,total_interactions",
}


# insights de vídeo da Página: nome na API -> campo no metrics.json (o primeiro que vier ganha)
FB_VIDEO_FIELDS = {
    "views": ("fb_reels_total_plays", "blue_reels_play_count", "total_video_views"),
    "views_3s": ("total_video_views",),
    "viewers": ("total_video_views_unique", "post_impressions_unique"),
    "complete_views": ("total_video_complete_views",),
    "avg_watch_s": ("total_video_avg_time_watched", "post_video_avg_time_watched"),  # vem em ms
    "watch_time_s": ("total_video_view_total_time", "post_video_view_time"),  # vem em ms
}
FB_VIDEO_FALLBACK = ("total_video_views,total_video_views_unique,total_video_complete_views,"
                     "total_video_avg_time_watched,total_video_view_total_time")
IG_WATCH = {"ig_reels_avg_watch_time": "avg_watch_s", "ig_reels_video_view_total_time": "watch_time_s"}  # ms
MAX_PAGES = 10  # 100 itens por página: cobre os 60 dias guardados mesmo com 10+ posts por dia
FB_VIDEO_ID = re.compile(r"/videos/(\w+)")
YT_ID = re.compile(r"(?:shorts/|youtu\.be/|watch\?v=)([\w-]+)")


def _title(post: dict) -> str:
    c = post.get("content", {})
    return c.get("title") or c.get("question") or c.get("ref_label") or post["id"]


def _get(url: str, **params) -> dict:
    resp = requests.get(url, params=params, timeout=60)
    data = resp.json()
    if resp.status_code != 200 or "error" in data:
        err = data.get("error", {}) if isinstance(data, dict) else {}
        raise PublishError(err.get("message") or resp.text[:200])
    return data


def _pages(url: str, **params) -> list[dict]:
    """Todos os itens de uma lista da Graph API, seguindo a paginação (até MAX_PAGES páginas)."""
    items: list[dict] = []
    data = _get(url, **params)
    for _ in range(MAX_PAGES):
        items += data.get("data", [])
        nxt = (data.get("paging") or {}).get("next")
        if not nxt:
            break
        data = _get(nxt)
    return items


def _is_permission_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "permission" in msg or "(#10)" in msg or "(#200)" in msg


def ig_insights(media_id: str, metrics: str, token: str, failed: list[str]) -> dict:
    """Insights de um post do Instagram. Se a Meta recusar o pedido junto (ex.: "Please reduce the
    amount of data"), tenta métrica por métrica e pula as que falharem. Só a falta de permissão
    sobe como erro (aí não adianta continuar)."""
    from .publishers.meta import GRAPH

    url = f"{GRAPH}/{media_id}/insights"
    try:
        items = _get(url, metric=metrics, access_token=token).get("data", [])
    except PublishError as exc:
        if _is_permission_error(exc):
            raise
        items = []
        for metric in metrics.split(","):
            try:
                items += _get(url, metric=metric, access_token=token).get("data", [])
            except PublishError as one:
                if _is_permission_error(one):
                    raise
                failed.append(f"{media_id}: {one}")
    out = {item["name"]: (item.get("values") or [{}])[0].get("value", 0) for item in items}
    for name, field in IG_WATCH.items():  # tempo assistido dos Reels vem em ms
        if isinstance(out.get(name), (int, float)):
            out[field] = round(out.pop(name) / 1000, 1)
    return out


def fb_video_insights(video_id: str, token: str) -> dict:
    """Visualizações, views de 3 s, pessoas, vídeos assistidos até o fim e tempo médio (s)."""
    from .publishers.meta import GRAPH

    data = _get(f"{GRAPH}/{video_id}/video_insights", access_token=token).get("data") or []
    if not data:
        data = _get(f"{GRAPH}/{video_id}/video_insights", metric=FB_VIDEO_FALLBACK,
                    access_token=token).get("data") or []
    raw = {}
    for item in data:
        value = (item.get("values") or [{}])[0].get("value")
        if isinstance(value, (int, float)) and item.get("name") not in raw:
            raw[item["name"]] = value
    out = {}
    for field, names in FB_VIDEO_FIELDS.items():
        value = next((raw[n] for n in names if n in raw), None)
        if value is None:
            continue
        out[field] = round(value / 1000, 1) if field.endswith("_s") else int(value)
    return out


def collect_meta(token: str, page_id: str | None, notes: list[str],
                 video_ids: set[str] | None = None) -> tuple[dict, dict]:
    """Devolve ({permalink_ig: métricas}, {id_fb: métricas}). Para os vídeos em video_ids
    (os publicados pelo sistema) busca também visualizações e tempo médio assistido."""
    from .publishers.meta import GRAPH, MetaAccount

    acc = MetaAccount(token, page_id)
    ig: dict[str, dict] = {}
    if acc.ig_id:
        media = _pages(f"{GRAPH}/{acc.ig_id}/media", access_token=acc.page_token, limit=100,
                       fields="id,permalink,timestamp,media_product_type,like_count,comments_count")
        insights_ok = True
        failed: list[str] = []
        for m in media:
            row = {"likes": m.get("like_count", 0), "comments": m.get("comments_count", 0)}
            metrics = IG_INSIGHTS.get(m.get("media_product_type"))
            if insights_ok and metrics:
                try:
                    row.update(ig_insights(m["id"], metrics, acc.page_token, failed))
                except PublishError as exc:
                    insights_ok = False
                    notes.append("Instagram: alcance, salvamentos e visualizações precisam da permissão "
                                 f"instagram_manage_insights no token (erro: {str(exc)[:120]})")
            ig[m.get("permalink", "").rstrip("/")] = row
        if failed:
            notes.append(f"Instagram: a Meta não devolveu algumas métricas de {len(set(failed))} post(s) "
                         f"(erro: {failed[-1][:120]})")
    fb: dict[str, dict] = {}
    posts = _pages(f"{GRAPH}/{acc.page_id}/posts", access_token=acc.page_token, limit=100,
                   fields="id,reactions.summary(true).limit(0),comments.summary(true).limit(0),shares")
    for p in posts:
        fb[p["id"]] = {"likes": p.get("reactions", {}).get("summary", {}).get("total_count", 0),
                       "comments": p.get("comments", {}).get("summary", {}).get("total_count", 0),
                       "shares": (p.get("shares") or {}).get("count", 0)}
    try:
        vids = _pages(f"{GRAPH}/{acc.page_id}/videos", access_token=acc.page_token, limit=100,
                      fields="id,likes.summary(true).limit(0),comments.summary(true).limit(0)")
        for v in vids:
            fb[v["id"]] = {"likes": v.get("likes", {}).get("summary", {}).get("total_count", 0),
                           "comments": v.get("comments", {}).get("summary", {}).get("total_count", 0)}
    except PublishError as exc:
        notes.append(f"Facebook (vídeos): {str(exc)[:120]}")
    for vid in sorted(video_ids or ()):
        try:
            extra = fb_video_insights(vid, acc.page_token)
        except PublishError as exc:
            notes.append("Facebook: visualizações e tempo médio dos vídeos precisam da permissão "
                         f"read_insights no token (erro: {str(exc)[:120]})")
            break
        if extra:
            fb[vid] = {**fb.get(vid, {}), **extra}
    return ig, fb


def collect_youtube(ids: list[str], notes: list[str]) -> dict:
    env = os.environ.get
    if not ids or not (env("YT_CLIENT_ID") and env("YT_CLIENT_SECRET") and env("YT_REFRESH_TOKEN")):
        return {}
    tok = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": env("YT_CLIENT_ID"), "client_secret": env("YT_CLIENT_SECRET"),
        "refresh_token": env("YT_REFRESH_TOKEN"), "grant_type": "refresh_token"}).json()
    if "access_token" not in tok:
        notes.append("YouTube: não consegui renovar o acesso")
        return {}
    out = {}
    for i in range(0, len(ids), 50):
        resp = requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=30,
                            params={"part": "statistics", "id": ",".join(ids[i:i + 50])},
                            headers={"Authorization": f"Bearer {tok['access_token']}"})
        if resp.status_code != 200:
            notes.append("YouTube: para ver visualizações, gere o refresh token com os escopos "
                         "youtube.upload e youtube.readonly (veja docs/PUBLICACAO.md)")
            return out
        for item in resp.json().get("items", []):
            st = item.get("statistics", {})
            out[item["id"]] = {"views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                               "comments": int(st.get("commentCount", 0))}
    for vid, extra in youtube_watch_time(ids, tok["access_token"], notes).items():
        if vid in out:
            out[vid].update(extra)
    return out


def youtube_watch_time(ids: list[str], access_token: str, notes: list[str]) -> dict:
    """Tempo médio e total assistido de cada vídeo (YouTube Analytics; os números chegam com
    1 a 2 dias de atraso). Precisa do escopo yt-analytics.readonly no refresh token."""
    out = {}
    today = date.today().isoformat()
    for i in range(0, len(ids), 200):
        resp = requests.get("https://youtubeanalytics.googleapis.com/v2/reports", timeout=30, params={
            "ids": "channel==MINE", "startDate": "2026-01-01", "endDate": today, "dimensions": "video",
            "metrics": "views,averageViewDuration,estimatedMinutesWatched",
            "filters": "video==" + ",".join(ids[i:i + 200])},
            headers={"Authorization": f"Bearer {access_token}"})
        if resp.status_code != 200:
            notes.append("YouTube: para ver o tempo assistido, gere o refresh token também com o escopo "
                         "yt-analytics.readonly (veja docs/PUBLICACAO.md)")
            return out
        data = resp.json()
        cols = [c["name"] for c in data.get("columnHeaders", [])]
        for row in data.get("rows") or []:
            r = dict(zip(cols, row))
            out[r["video"]] = {"avg_watch_s": round(float(r.get("averageViewDuration") or 0), 1),
                               "watch_time_s": round(float(r.get("estimatedMinutesWatched") or 0) * 60, 1)}
    return out


def collect(today: date) -> dict:
    notes: list[str] = []
    limit = (today - timedelta(days=KEEP_DAYS)).isoformat()
    posts = [p for p in state.load_queue() + state.load_history()
             if p.get("date", "") >= limit and p.get("publish_links")]
    ig, fb = {}, {}
    fb_videos = {m.group(1) for p in posts
                 if (m := FB_VIDEO_ID.search(p["publish_links"].get("facebook", "") or ""))}
    if os.environ.get("META_ACCESS_TOKEN"):
        try:
            ig, fb = collect_meta(os.environ["META_ACCESS_TOKEN"], os.environ.get("META_PAGE_ID") or None,
                                  notes, fb_videos)
        except PublishError as exc:
            notes.append(f"Meta: {str(exc)[:160]}")
    yt_ids = {}
    for p in posts:
        m = YT_ID.search(p["publish_links"].get("youtube", "") or "")
        if m:
            yt_ids[m.group(1)] = p["id"]
    yt = collect_youtube(list(yt_ids), notes)

    out = {}
    for p in posts:
        links = p["publish_links"]
        row = {"type": p.get("type"), "date": p.get("date"), "time": p.get("time"), "title": _title(p),
               "hook": captions.hook_of(p),
               **({"repost_of": p["repost_of"]} if p.get("repost_of") else {}),
               "links": {k: v for k, v in links.items() if str(v).startswith("http")}}
        if links.get("instagram"):
            row["instagram"] = ig.get(links["instagram"].rstrip("/"))
        fb_link = links.get("facebook", "") or ""
        fb_id = fb_link.rstrip("/").split("/")[-1]
        if fb_id:
            row["facebook"] = fb.get(fb_id) or fb.get(fb_id.split("_")[-1])
        m = YT_ID.search(links.get("youtube", "") or "")
        if m:
            row["youtube"] = yt.get(m.group(1))
        out[p["id"]] = row
    return {"updated_at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"),
            "notes": sorted(set(notes)), "posts": out}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.metrics")
    parser.add_argument("--out", default="metrics.json")
    args = parser.parse_args(argv)
    data = collect(date.today())
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"métricas de {len(data['posts'])} post(s); avisos: {data['notes'] or 'nenhum'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
