"""Auditoria da Bíblia local: procura restos de tradução automática e erros de texto.

  python scripts/audit_bible.py [--limit 60]

Não altera nada: só lista versículos suspeitos para revisão humana.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import bible  # noqa: E402

ENGLISH = re.compile(r"\b(the|and|of|that|with|which|shall|unto|thou|thee|lord god|said)\b", re.I)
META = re.compile(r"[\[\]{}<>*_#`|\\]|https?:|\\[a-z]+\d*|\bUSFM\b", re.I)
ODD_CHARS = re.compile(r"[^\w\s.,;:!?'\"“”‘’()\-—–…«»áàâãäéèêíìîóòôõöúùûüçñÁÀÂÃÉÈÊÍÓÔÕÚÇ]")
REPEAT = re.compile(r"\b(\w{3,})\s+\1\b", re.I)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args()
    with gzip.open(bible.BIBLE_PATH, "rt", encoding="utf-8") as fh:
        data = json.load(fh)

    findings: list[tuple[str, str, str]] = []
    lengths = []
    total = 0
    for book, chapters in data.items():
        for ch, verses in chapters.items():
            for i, text in enumerate(verses, start=1):
                total += 1
                ref = f"{bible.BOOK_NAMES.get(book, book)} {ch}:{i}"
                lengths.append(len(text))
                if not text.strip():
                    findings.append((ref, "vazio", ""))
                    continue
                if bible.SUSPICIOUS.search(text):
                    findings.append((ref, "trava atual", text))
                if META.search(text):
                    findings.append((ref, "marcação/metadado", text))
                if ENGLISH.search(text):
                    findings.append((ref, "inglês?", text))
                if REPEAT.search(text):
                    findings.append((ref, "palavra repetida", text))
                if ODD_CHARS.search(text):
                    findings.append((ref, "caractere estranho", text))
                # Minúscula no início, falta de pontuação final e versículos idênticos
                # são normais na Bíblia (frases que continuam, fórmulas repetidas): ignorados.
                if len(text) < 12 or len(text) > 600:
                    findings.append((ref, "tamanho incomum", text))
    avg = sum(lengths) / len(lengths)
    print(f"{total} versículos; tamanho médio {avg:.0f}; máximo {max(lengths)}")
    print(Counter(w for _, w, _ in findings).most_common())
    shown = 0
    for ref, why, text in findings:
        print(f"- {ref} [{why}] {text[:160]}")
        shown += 1
        if shown >= args.limit:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
