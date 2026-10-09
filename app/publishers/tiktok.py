"""TikTok: envia o Reel para os RASCUNHOS/caixa de entrada do app (Content Posting
API, escopo video.upload). Você abre o TikTok, escolhe uma música do app,
cola a legenda e publica.

A autorização é feita uma vez pelo painel (botão "Conectar TikTok"). O token de
renovação fica em state/tiktok.json CRIPTOGRAFADO (AES-GCM) com uma chave
derivada de MEDIA_SIGNING_SECRET; só o painel e o GitHub Actions conseguem ler.
"""
from __future__ import annotations

import base64
import hashlib
import os
import time
from pathlib import Path

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import PublishError, Publisher

API = "https://open.tiktokapis.com/v2"


def _key(secret: str) -> bytes:
    return hashlib.sha256(f"{secret}|tiktok".encode()).digest()


def encrypt(text: str, secret: str) -> str:
    iv = os.urandom(12)
    return base64.b64encode(iv + AESGCM(_key(secret)).encrypt(iv, text.encode(), None)).decode()


def decrypt(blob: str, secret: str) -> str:
    raw = base64.b64decode(blob)
    return AESGCM(_key(secret)).decrypt(raw[:12], raw[12:], None).decode()


class TikTokPublisher(Publisher):
    platform = "tiktok"

    def __init__(self, auth: dict, client_key: str, client_secret: str, secret: str):
        """auth = conteúdo de state/tiktok.json. Renova o token de acesso na hora."""
        if not auth.get("refresh_token_enc"):
            raise PublishError("TikTok não conectado: use o botão 'Conectar TikTok' no painel")
        try:
            refresh = decrypt(auth["refresh_token_enc"], secret)
        except Exception as exc:  # chave trocada ou arquivo corrompido
            raise PublishError("não consegui ler a conexão do TikTok; conecte de novo pelo painel") from exc
        try:
            resp = requests.post(f"{API}/oauth/token/", timeout=30, data={
                "client_key": client_key, "client_secret": client_secret,
                "grant_type": "refresh_token", "refresh_token": refresh})
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise PublishError(f"falha ao falar com o TikTok: {exc}") from exc
        if "access_token" not in data:
            raise PublishError(f"TikTok recusou a conexão ({data.get('error_description') or data.get('error')}); "
                               "conecte de novo pelo painel")
        self.token = data["access_token"]
        # o TikTok pode devolver um token de renovação novo: guardamos sempre o mais recente
        self.updated_auth = {
            **auth,
            "refresh_token_enc": encrypt(data.get("refresh_token", refresh), secret),
            "refresh_expires_at": int(time.time()) + int(data.get("refresh_expires_in", 0) or 0),
        }

    def supports(self, post: dict) -> bool:
        return bool(post.get("media", {}).get("video_silent"))

    def _post(self, path: str, body: dict) -> dict:
        resp = requests.post(f"{API}{path}", json=body, timeout=60, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json; charset=UTF-8"})
        try:
            data = resp.json()
        except ValueError:
            raise PublishError(f"TikTok: resposta inválida ({resp.status_code})")
        err = data.get("error") or {}
        if resp.status_code != 200 or err.get("code") not in (None, "ok"):
            raise PublishError(f"TikTok: {err.get('code')} — {err.get('message') or resp.text[:200]}")
        return data.get("data", {})

    def publish(self, post: dict, media_dir: Path, media_url) -> str:
        video = media_dir / post["media"]["video_silent"]  # sem música: você escolhe a do app
        if not video.exists():
            raise PublishError(f"arquivo de vídeo não encontrado: {video.name}")
        size = video.stat().st_size
        init = self._post("/post/publish/inbox/video/init/", {"source_info": {
            "source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}})
        try:
            with video.open("rb") as fh:
                up = requests.put(init["upload_url"], data=fh, timeout=300, headers={
                    "Content-Type": "video/mp4", "Content-Length": str(size),
                    "Content-Range": f"bytes 0-{size - 1}/{size}"})
        except requests.RequestException as exc:
            raise PublishError(f"falha no envio ao TikTok: {exc}") from exc
        if up.status_code not in (200, 201):
            raise PublishError(f"TikTok recusou o arquivo ({up.status_code}): {up.text[:200]}")
        publish_id = init.get("publish_id", "")
        for _ in range(12):  # até ~1 min para confirmar que chegou na caixa de entrada
            status = self._post("/post/publish/status/fetch/", {"publish_id": publish_id}).get("status")
            if status in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
                return "rascunho no app do TikTok"
            if status == "FAILED":
                raise PublishError("TikTok não conseguiu processar o vídeo")
            time.sleep(5)
        return "enviado ao TikTok (processando)"
