"""Converte o arquivo VPL da Bíblia Portuguesa Mundial (eBible.org) para o
formato compacto usado pelo sistema: data/bible/bpm.json.gz

Uso:
    curl -LO https://ebible.org/Scriptures/porbrbsl_vpl.zip
    unzip porbrbsl_vpl.zip
    python scripts/build_bible.py porbrbsl_vpl.txt

Só os 66 livros do cânon protestante são mantidos.
"""
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.bible import BOOKS  # noqa: E402

LINE = re.compile(r"^(\w{3}) (\d+):(\d+) (.*)$")


# A BPM é um rascunho em revisão e alguns versículos trazem "lixo" de
# tradução automática no final (ex.: Nm 13:33, Lc 7:50, Sl 88:18).
ARTIFACTS = [
    re.compile(r"\s*Aqui está a tradução.*$", re.S),
    re.compile(r"\s*```\w*\s*$"),
]


def clean(text: str) -> str:
    """Remove artefatos de tradução e espaços que sobraram de notas de rodapé
    (ex.: 'unigênito ,')."""
    for pattern in ARTIFACTS:
        text = pattern.sub("", text)
    text = re.sub(r"\s+([,.;:!?”’)])", r"\1", text)
    text = re.sub(r"([“‘(])\s+", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def main(src: str) -> None:
    codes = {b[0] for b in BOOKS}
    data: dict[str, dict[str, list[str]]] = {}
    for raw in Path(src).read_text(encoding="utf-8").splitlines():
        m = LINE.match(raw.strip())
        if not m:
            continue
        code, ch, vs, text = m.group(1), m.group(2), int(m.group(3)), clean(m.group(4))
        if code not in codes:
            continue
        chapter = data.setdefault(code, {}).setdefault(ch, [])
        # garante que o índice da lista = número do versículo - 1
        while len(chapter) < vs - 1:
            chapter.append("")
        chapter.append(text)
    missing = codes - data.keys()
    if missing:
        raise SystemExit(f"Livros ausentes: {sorted(missing)}")
    out = Path(__file__).resolve().parents[1] / "data" / "bible" / "bpm.json.gz"
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"OK: {out} ({sum(len(v) for b in data.values() for v in b.values())} versículos)")


if __name__ == "__main__":
    main(sys.argv[1])
