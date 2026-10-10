"""YouTube pela YouTube Data API v3 (upload resumível).

Segredos: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN (veja docs/PUBLICACAO.md).
Só posts com vídeo: o quiz (vertical, até 60 s, vira Short) e o vídeo longo de quiz
(16:9, ~10 min, vira vídeo normal, com miniatura e capítulos na descrição).

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
        long_video = post.get("type") == "compilation"
        meta = {
            "snippet": {"title": yt["title"][:100], "description": yt["description"][:4900],
                        "categoryId": "27" if long_video else "22", "defaultLanguage": "pt-BR"},
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
            video_id = up.json()["id"]
            if long_video:
                self._thumbnail(video_id, media_dir / post["media"].get("thumbnail", "miniatura.jpg"))
                return f"https://youtu.be/{video_id}"
            return f"https://youtube.com/shorts/{video_id}"
        except requests.RequestException as exc:
            raise PublishError(f"falha no envio ao YouTube: {exc}") from exc

    def _thumbnail(self, video_id: str, image: Path) -> None:
        """Miniatura personalizada. Se a conta ainda não for verificada, o YouTube recusa: segue sem."""
        if not image.exists():
            return
        try:
            resp = requests.post("https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                                 params={"videoId": video_id}, data=image.read_bytes(), timeout=120,
                                 headers={"Authorization": f"Bearer {self.token}", "Content-Type": "image/jpeg"})
            if resp.status_code != 200:
                print(f"· miniatura não aplicada ({resp.status_code}): verifique o canal em youtube.com/verify")
        except requests.RequestException as exc:
            print(f"· miniatura não aplicada: {exc}")
