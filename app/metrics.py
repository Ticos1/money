"""Coleta métricas dos posts publicados (Instagram, Facebook e YouTube).

  python -m app.metrics --out metrics.json

Roda junto da publicação (GitHub Actions) e grava state/metrics.json, que o
painel mostra na aba "Métricas". Tudo pelas APIs oficiais e com os mesmos
tokens já configurados. Se faltar alguma permissão (ex.: alcance/salvamentos do
Instagram precisam de instagram_manage_insights; visualizações e tempo médio dos
vídeos do Facebook precisam de read_insights), coleta o que der e avisa.
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
    "REELS": "reach,saved,shares,views,total_interactions",
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
        data = _get(f"{GRAPH}/{acc.ig_id}/media", access_token=acc.page_token, limit=100,
                    fields="id,permalink,timestamp,media_product_type,like_count,comments_count")
        insights_ok = True
        for m in data.get("data", []):
            row = {"likes": m.get("like_count", 0), "comments": m.get("comments_count", 0)}
            metrics = IG_INSIGHTS.get(m.get("media_product_type"))
            if insights_ok and metrics:
                try:
                    ins = _get(f"{GRAPH}/{m['id']}/insights", metric=metrics, access_token=acc.page_token)
                    for item in ins.get("data", []):
                        row[item["name"]] = (item.get("values") or [{}])[0].get("value", 0)
                except PublishError as exc:
                    insights_ok = False
                    notes.append("Instagram: alcance, salvamentos e visualizações precisam da permissão "
                                 f"instagram_manage_insights no token (erro: {str(exc)[:120]})")
            ig[m.get("permalink", "").rstrip("/")] = row
    fb: dict[str, dict] = {}
    posts = _get(f"{GRAPH}/{acc.page_id}/posts", access_token=acc.page_token, limit=100,
                 fields="id,reactions.summary(true).limit(0),comments.summary(true).limit(0),shares")
    for p in posts.get("data", []):
        fb[p["id"]] = {"likes": p.get("reactions", {}).get("summary", {}).get("total_count", 0),
                       "comments": p.get("comments", {}).get("summary", {}).get("total_count", 0),
                       "shares": (p.get("shares") or {}).get("count", 0)}
    try:
        vids = _get(f"{GRAPH}/{acc.page_id}/videos", access_token=acc.page_token, limit=100,
                    fields="id,likes.summary(true).limit(0),comments.summary(true).limit(0)")
        for v in vids.get("data", []):
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
