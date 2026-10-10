"""Avisa por e-mail quando uma publicação falha.

Roda no fim do workflow "Publicar nas redes", depois de salvar o resultado. Se alguma rede deu erro
(primeira vez ou última tentativa), sai com erro: o GitHub então manda um e-mail de "workflow
falhou" para você. Sem servidor, sem custo e sem segredo extra.

  python -m app.alert patch.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import config, state

NAMES = {"instagram": "Instagram", "facebook": "Facebook", "youtube": "YouTube", "stories": "Stories",
         "tiktok": "TikTok"}


def problems(patch: dict, queue: list[dict], max_attempts: int) -> list[str]:
    """Erros novos desta rodada: o primeiro de cada post/rede e o da última tentativa."""
    by_id = {p["id"]: p for p in queue}
    out = []
    for post_id, nets in (patch.get("publish_results") or {}).items():
        for net, result in nets.items():
            if not result.get("error"):
                continue
            attempts = ((by_id.get(post_id, {}).get("publish_errors") or {}).get(net) or {}).get("attempts", 1)
            if attempts == 1 or attempts >= max_attempts:
                tail = " — DESISTIU (3 tentativas); abra o post no painel e toque em Publicar agora" \
                    if attempts >= max_attempts else ""
                out.append(f"{post_id} → {NAMES.get(net, net)}: {result['error']}{tail}")
    return out


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    patch = json.loads(Path(args[0]).read_text(encoding="utf-8")) if args and Path(args[0]).exists() else {}
    max_attempts = int(config.load_settings().get("publishing", {}).get("max_attempts", 3))
    found = problems(patch, state.load_queue(), max_attempts)
    if not found:
        print("Sem erros de publicação.")
        return 0
    print("::error::Falha ao publicar:")
    for line in found:
        print(f"::error::{line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
