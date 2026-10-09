"""Publicadores automáticos (Fases 2, 3 e 4 — ainda não ativados).

Cada rede terá um módulo com uma classe que segue `Publisher`. O pipeline vai
chamar `publish(post)` para cada post APROVADO cujo horário chegou e marcar
`post["published"][rede]` com a data, igual ao que você faz hoje no painel.

Plano (somente APIs oficiais, nada que arrisque a conta):
  youtube.py   Fase 2 — YouTube Data API v3 (videos.insert), vídeo COM música
  meta.py      Fase 3 — Instagram Graph API (Reels/feed) + Facebook Pages API
  tiktok.py    Fase 4 — TikTok Content Posting API (Direct Post)
  Kwai         sem API pública de postagem: continua manual pelo painel
  telegram.py / whatsapp.py   futuro (fora do escopo agora)

Veja docs/FASES.md para o passo a passo de cada aprovação.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class Publisher(ABC):
    platform: str = ""

    def __init__(self, settings: dict):
        self.settings = settings

    @abstractmethod
    def publish(self, post: dict, media_dir: str) -> str:
        """Publica o post e devolve o ID/URL criado na rede."""


def available_publishers(settings: dict) -> list[Publisher]:
    """Por enquanto nenhum: a Fase 1 é postagem manual pelo painel."""
    return []
