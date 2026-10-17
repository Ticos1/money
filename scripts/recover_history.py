"""Recupera do histórico do Git os posts publicados que foram apagados por uma cópia não publicada.

Até 17/10/2026 o cron do GitHub chegava horas atrasado, o gerador refazia os primeiros posts do
dia (que já tinham saído da fila) e a cópia sobrescrevia o original em state/history.json, levando
junto os links e, portanto, as métricas. Este script procura, em todos os commits, a última versão
publicada de cada post que hoje está no histórico sem nenhuma publicação, e a coloca de volta.

Uso: python scripts/recover_history.py [--dry-run]   (pode rodar mais de uma vez)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import state  # noqa: E402

FILES = ("state/queue.json", "state/history.json")


def _published(post: dict) -> list[str]:
    return [k for k, v in (post.get("published") or {}).items() if v]


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def find_originals(lost: set[str]) -> dict[str, dict]:
    """id → versão mais recente com o maior número de redes publicadas."""
    best: dict[str, dict] = {}
    for commit in _git("log", "--format=%h", "--", *FILES).stdout.split():  # do mais novo ao mais antigo
        for name in FILES:
            res = _git("show", f"{commit}:{name}")
            if res.returncode:
                continue
            for post in json.loads(res.stdout).get("posts", []):
                if post["id"] in lost and _published(post):
                    cur = best.get(post["id"])
                    if not cur or len(_published(post)) > len(_published(cur)):
                        best[post["id"]] = post
    return best


def main(argv: list[str]) -> int:
    history = state.load_history()
    lost = {p["id"] for p in history if not _published(p)}
    originals = find_originals(lost)
    for post_id in sorted(originals):
        print(f"{post_id}: recuperado ({', '.join(_published(originals[post_id]))})")
    print(f"{len(originals)} de {len(lost)} posts sem publicação recuperados")
    if originals and "--dry-run" not in argv:
        for post in originals.values():
            post.pop("media", None)
        state.save_history([originals.get(p["id"], p) for p in history])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
