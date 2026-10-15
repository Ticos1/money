"""Publicação automática nas redes (somente APIs oficiais).

  meta.py      Instagram (feed e Reels) + Facebook (Página) — Graph API da Meta
  youtube.py   YouTube Shorts — YouTube Data API v3 (fica privado até a auditoria)
  TikTok       depende da auditoria do app no TikTok (veja docs/FASES.md)
  Kwai         sem API pública de postagem: continua manual pelo painel
  WhatsApp     canal sem API oficial de postagem: manual pelo painel (docs/WHATSAPP.md)

Quem decide QUANDO publicar é app/publish.py: posts APROVADOS cujo horário
já chegou. Cada publicador só cuida de COMO publicar numa rede.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class PublishError(RuntimeError):
    pass


class Publisher(ABC):
    platform: str = ""

    @abstractmethod
    def supports(self, post: dict) -> bool:
        """Este tipo de post pode ir para esta rede?"""

    @abstractmethod
    def publish(self, post: dict, media_dir: Path, media_url) -> str:
        """Publica e devolve o link (ou ID) do post criado.

        media_dir: pasta local com os arquivos do post.
        media_url(nome_do_arquivo): link público temporário para o arquivo.
        """
