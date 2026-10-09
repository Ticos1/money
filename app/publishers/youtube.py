"""YouTube Shorts pela YouTube Data API v3 (upload resumível).

Segredos: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN (veja docs/PUBLICACAO.md).
Só posts com vídeo (o quiz). Vídeo vertical com até 60 s vira Short.

Atenção: enquanto o projeto no Google Cloud não passar pela auditoria do
YouTube, os vídeos enviados pela API ficam PRIVADOS (regra do YouTube).
"""
from __future__ import annotations

from pathlib import Path

import requests

from . import PublishError, Publisher

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"


class YouTubePublisher(Publisher):
    platform = "youtube"

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        try:
            resp = requests.post(TOKEN_URL, data={
                "client_id": client_id, "client_secret": client_secret,
                "refresh_token": refresh_token, "grant_type": "refresh_token"}, timeout=30)
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise PublishError(f"falha ao falar com o Google: {exc}") from exc
        if "access_token" not in data:
            raise PublishError(f"Google recusou o token: {data.get('error_description') or data.get('error')}")
        self.token = data["access_token"]

    def supports(self, post: dict) -> bool:
        return bool(post.get("media", {}).get("video_music"))

    def publish(self, post: dict, media_dir: Path, media_url) -> str:
        video = media_dir / post["media"]["video_music"]
        if not video.exists():
            raise PublishError(f"arquivo de vídeo não encontrado: {video.name}")
        yt = post["captions"]["youtube"]
        meta = {
            "snippet": {"title": yt["title"][:100], "description": yt["description"][:4900],
                        "categoryId": "22", "defaultLanguage": "pt-BR"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        }
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            init = requests.post(UPLOAD_URL, json=meta, timeout=60, headers={
                **headers, "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(video.stat().st_size)})
            if init.status_code != 200:
                raise PublishError(f"YouTube: {init.text[:300]}")
            with video.open("rb") as fh:
                up = requests.put(init.headers["Location"], data=fh, timeout=600,
                                  headers={**headers, "Content-Type": "video/mp4"})
            if up.status_code not in (200, 201):
                raise PublishError(f"YouTube: {up.text[:300]}")
            return f"https://youtube.com/shorts/{up.json()['id']}"
        except requests.RequestException as exc:
            raise PublishError(f"falha no envio ao YouTube: {exc}") from exc
