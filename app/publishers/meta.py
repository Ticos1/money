"""Instagram e Facebook pela Graph API oficial da Meta.

Precisa de UM segredo: META_ACCESS_TOKEN — o token da sua Página do Facebook
(gerado a partir de um token de usuário de longa duração, ele não expira).
Também aceita um token de usuário; nesse caso a Página é descoberta sozinha
(use META_PAGE_ID se você tiver mais de uma Página).

O que vai para cada rede:
  Versículo (imagem) → Instagram: foto 4:5 no feed · Facebook: foto
  Quiz (vídeo)       → Instagram: Reels (com música) · Facebook: vídeo
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from . import PublishError, Publisher

GRAPH = "https://graph.facebook.com/" + os.environ.get("META_GRAPH_VERSION", "v25.0")


def _call(method: str, path: str, **params) -> dict:
    try:
        resp = requests.request(method, f"{GRAPH}/{path}", data=params if method == "POST" else None,
                                params=params if method == "GET" else None, timeout=120)
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise PublishError(f"falha de conexão com a Meta: {exc}") from exc
    if resp.status_code != 200 or "error" in data:
        err = data.get("error", {}) if isinstance(data, dict) else {}
        message = " ".join(str(err.get("message") or resp.text[:300]).split())
        if err.get("code") == 190 and "permission" in message:
            raise PublishError("O token da Meta (META_ACCESS_TOKEN) está sem as permissões da Página. Gere o token "
                               "de novo marcando TODAS as permissões e atualize o segredo "
                               "(docs/PUBLICACAO.md, 'Token da Meta com erro 190').")
        raise PublishError(f"Meta: {message} (código {err.get('code')})")
    return data


class MetaAccount:
    """Descobre a Página e o Instagram ligado a partir do token (uma vez por execução)."""

    def __init__(self, token: str, page_id: str | None = None):
        self.user_token = token
        self.page_token = token
        self.page_id = page_id
        self.ig_id = None
        self._discover()

    def _discover(self) -> None:
        try:  # token de Página: /me é a própria Página
            me = _call("GET", "me", fields="id,name,instagram_business_account", access_token=self.page_token)
            if not self.page_id or me["id"] == self.page_id:
                self.page_id = me["id"]
                self.ig_id = (me.get("instagram_business_account") or {}).get("id")
                return
        except PublishError:
            pass
        # token de usuário: procura a Página em /me/accounts
        pages = _call("GET", "me/accounts", fields="id,name,access_token,instagram_business_account",
                      access_token=self.user_token).get("data", [])
        if self.page_id:
            pages = [p for p in pages if p["id"] == self.page_id]
        if not pages:
            raise PublishError("nenhuma Página do Facebook encontrada para esse token")
        page = pages[0]
        self.page_id, self.page_token = page["id"], page["access_token"]
        self.ig_id = (page.get("instagram_business_account") or {}).get("id")


def _wait_container(container_id: str, token: str, timeout: int = 600) -> None:
    """Vídeos são processados pela Meta antes de publicar: espera ficar FINISHED."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _call("GET", container_id, fields="status_code,status", access_token=token)
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"Instagram recusou a mídia: {status.get('status')}")
        time.sleep(8)
    raise PublishError("Instagram demorou demais para processar o vídeo")


class InstagramPublisher(Publisher):
    platform = "instagram"

    def __init__(self, account: MetaAccount):
        if not account.ig_id:
            raise PublishError("a Página não tem um Instagram profissional conectado")
        self.acc = account

    def supports(self, post: dict) -> bool:
        return True

    def publish(self, post: dict, media_dir: Path, media_url) -> str:
        token, ig = self.acc.page_token, self.acc.ig_id
        caption = post["captions"]["instagram"][:2200]
        media = post["media"]
        if media.get("video_music"):
            container = _call("POST", f"{ig}/media", media_type="REELS", share_to_feed="true",
                              video_url=media_url(media["video_music"]), caption=caption,
                              access_token=token)["id"]
        else:
            image = "imagem_vertical.jpg" if "imagem_vertical.jpg" in media["images"] else media["images"][0]
            container = _call("POST", f"{ig}/media", image_url=media_url(image), caption=caption,
                              access_token=token)["id"]
        _wait_container(container, token)
        media_id = _call("POST", f"{ig}/media_publish", creation_id=container, access_token=token)["id"]
        try:
            return _call("GET", media_id, fields="permalink", access_token=token).get("permalink", media_id)
        except PublishError:
            return media_id


class FacebookPublisher(Publisher):
    platform = "facebook"

    def __init__(self, account: MetaAccount):
        self.acc = account

    def supports(self, post: dict) -> bool:
        return True

    def publish(self, post: dict, media_dir: Path, media_url) -> str:
        token, page = self.acc.page_token, self.acc.page_id
        text = post["captions"]["facebook"]
        media = post["media"]
        if media.get("video_music"):
            vid = _call("POST", f"{page}/videos", file_url=media_url(media["video_music"]),
                        description=text, access_token=token)["id"]
            return f"https://www.facebook.com/{page}/videos/{vid}"
        image = "imagem_vertical.jpg" if "imagem_vertical.jpg" in media["images"] else media["images"][0]
        res = _call("POST", f"{page}/photos", url=media_url(image), message=text, access_token=token)
        return f"https://www.facebook.com/{res.get('post_id') or res['id']}"


class InstagramStoryPublisher(Publisher):
    """Stories do Instagram: imagem 9:16 (Versículo, Você sabia?) ou o vídeo do quiz."""
    platform = "stories"

    def __init__(self, account: MetaAccount):
        if not account.ig_id:
            raise PublishError("a Página não tem um Instagram profissional conectado")
        self.acc = account

    def supports(self, post: dict) -> bool:
        media = post.get("media", {})
        return bool(media.get("video_music") or "imagem_story.jpg" in media.get("images", []))

    def publish(self, post: dict, media_dir: Path, media_url) -> str:
        token, ig = self.acc.page_token, self.acc.ig_id
        media = post["media"]
        if media.get("video_music"):
            container = _call("POST", f"{ig}/media", media_type="STORIES",
                              video_url=media_url(media["video_music"]), access_token=token)["id"]
        else:
            container = _call("POST", f"{ig}/media", media_type="STORIES",
                              image_url=media_url("imagem_story.jpg"), access_token=token)["id"]
        _wait_container(container, token)
        media_id = _call("POST", f"{ig}/media_publish", creation_id=container, access_token=token)["id"]
        return f"story {media_id}"
