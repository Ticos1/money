"""Apaga do histórico os posts que nunca saíram em nenhuma rede e só ocupam espaço:

- "pending" (nunca aprovados): re-renderizações (-v4) e posts esquecidos;
- cópias aprovadas mas não publicadas de um horário cujo post saiu nas redes (geração repetida).

Posts publicados, rejeitados e os de hoje em diante ficam. Desde 17/10/2026 o gerador não refaz
posts que já estão no histórico e o arquivamento descarta os "pending", então isto é uma limpeza única.

Uso: python scripts/clean_history.py [--dry-run]   (pode rodar mais de uma vez)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import state  # noqa: E402


def stale(posts: list[dict], today: str) -> list[dict]:
    published_slots = {(p["date"], p.get("time"), p.get("type")) for p in posts if state._was_published(p)}
    out = []
    for p in posts:
        if state._was_published(p) or p.get("date", "") >= today:
            continue
        if p.get("status") == "pending" or (p.get("status") == "approved"
                                            and (p["date"], p.get("time"), p.get("type")) in published_slots):
            out.append(p)
    return out


def main(argv: list[str]) -> int:
    history = state.load_history()
    gone = stale(history, date.today().isoformat())
    for p in sorted(gone, key=lambda p: p["id"]):
        print(f"apagar {p['id']} ({p.get('status')})")
    print(f"{len(gone)} de {len(history)} posts do histórico")
    if gone and "--dry-run" not in argv:
        ids = {p["id"] for p in gone}
        state.save_history([p for p in history if p["id"] not in ids])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
