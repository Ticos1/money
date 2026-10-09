"""Validação de conteúdo contra a Bíblia local.

Regras (valem para o banco e para o que vier da Groq):
- a referência precisa existir na Bíblia Portuguesa Mundial;
- quiz/curiosidade: a "evidência" precisa estar literalmente no texto;
- quiz: a alternativa correta precisa estar apoiada pelo texto, e nenhuma
  alternativa errada pode também estar (evita pergunta com duas respostas).

Uso: python -m app.validate     (valida o banco inteiro e mostra os erros)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import bible

BANK_DIR = Path(__file__).resolve().parents[1] / "content" / "bank"
MAX_ON_SCREEN = 110


class ContentError(ValueError):
    pass


def _ref_text(item: dict) -> tuple[bible.Reference, str]:
    try:
        ref = bible.parse_reference(item.get("ref", ""))
        return ref, bible.get_text(ref)
    except bible.BibleError as exc:
        raise ContentError(str(exc)) from exc


def validate_verse(item: dict) -> dict:
    ref, _ = _ref_text(item)
    try:
        text = bible.display_text(ref, item.get("skip_prefix", ""))
    except bible.BibleError as exc:
        raise ContentError(str(exc)) from exc
    for field in ("reflection", "on_screen"):
        if not str(item.get(field, "")).strip():
            raise ContentError(f"campo vazio: {field}")
    if len(item["on_screen"]) > MAX_ON_SCREEN:
        raise ContentError(f"on_screen longo demais ({len(item['on_screen'])} > {MAX_ON_SCREEN})")
    if len(text) > 420:
        raise ContentError(f"versículo longo demais para o vídeo ({len(text)} caracteres)")
    return {**item, "ref_label": ref.label, "ref_key": ref.key, "verse_text": text}


def validate_quiz(item: dict) -> dict:
    ref, text = _ref_text(item)
    options = item.get("options") or []
    answer = item.get("answer")
    if len(options) != 4 or len(set(o.lower() for o in options)) != 4:
        raise ContentError("o quiz precisa de 4 alternativas diferentes")
    if not isinstance(answer, int) or not 0 <= answer < 4:
        raise ContentError("índice da resposta inválido")
    if not str(item.get("question", "")).strip():
        raise ContentError("pergunta vazia")
    if not bible.contains_phrase(text, item.get("evidence", "")):
        raise ContentError(f"evidência não encontrada em {ref.label}: {item.get('evidence')!r}")
    if not bible.answer_supported(text, options[answer]):
        raise ContentError(f"resposta {options[answer]!r} não aparece em {ref.label}")
    for i, opt in enumerate(options):
        if i != answer and bible.answer_supported(text, opt):
            raise ContentError(f"alternativa errada {opt!r} também aparece no texto (ambígua)")
    if any(len(o) > 48 for o in options):
        raise ContentError("alternativa longa demais para o vídeo (máx. 48 caracteres)")
    if len(item["question"]) > 140:
        raise ContentError("pergunta longa demais (máx. 140 caracteres)")
    return {**item, "ref_label": ref.label, "ref_key": ref.key, "passage": text}


def validate_curiosity(item: dict) -> dict:
    ref, text = _ref_text(item)
    if not bible.contains_phrase(text, item.get("evidence", "")):
        raise ContentError(f"evidência não encontrada em {ref.label}: {item.get('evidence')!r}")
    for field in ("title", "text"):
        if not str(item.get(field, "")).strip():
            raise ContentError(f"campo vazio: {field}")
    return {**item, "ref_label": ref.label, "ref_key": ref.key, "passage": text}


VALIDATORS = {
    "verse": ("verses.json", validate_verse),
    "quiz": ("quizzes.json", validate_quiz),
    "curiosity": ("curiosities.json", validate_curiosity),
}


def load_bank(kind: str) -> list[dict]:
    filename, _ = VALIDATORS[kind]
    return json.loads((BANK_DIR / filename).read_text(encoding="utf-8"))


def validate(kind: str, item: dict) -> dict:
    return VALIDATORS[kind][1](item)


def main() -> int:
    errors = 0
    for kind in VALIDATORS:
        items = load_bank(kind)
        ids = [i.get("id") for i in items]
        dupes = {x for x in ids if ids.count(x) > 1}
        if dupes:
            print(f"[{kind}] IDs repetidos: {sorted(dupes)}")
            errors += len(dupes)
        refs: dict[str, str] = {}
        ok = 0
        for item in items:
            try:
                checked = validate(kind, item)
                ok += 1
                if kind == "verse":
                    if checked["ref_key"] in refs:
                        print(f"[{kind}] {item['id']}: mesmo versículo de {refs[checked['ref_key']]}")
                        errors += 1
                    refs[checked["ref_key"]] = item["id"]
            except ContentError as exc:
                errors += 1
                print(f"[{kind}] {item.get('id')}: {exc}")
        print(f"{kind}: {ok}/{len(items)} válidos")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
