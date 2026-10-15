"""Escolha do conteúdo de cada post: banco local + complemento da Groq.

Ordem de decisão:
1. Às vezes (config groq.new_content_ratio) tenta gerar conteúdo NOVO na Groq.
   Ele só é aceito se passar na mesma validação bíblica do banco.
2. Senão (ou se a Groq falhar), pega um item do banco ainda não usado.
3. Se o banco acabou e a Groq falhou, reutiliza o item usado há mais tempo,
   para o post do dia nunca deixar de sair.
"""
from __future__ import annotations

import hashlib
import random
import re
from datetime import date, timedelta

from . import bible, validate
from .groq_client import GroqClient, GroqUnavailable

SYSTEM_PROMPT = (
    "Você é um redator cristão evangélico brasileiro. Escreve em português do Brasil, "
    "com tom respeitoso, acolhedor e fiel à Bíblia, sem polêmicas denominacionais, "
    "sem promessas de prosperidade e sem inventar fatos. Responda somente com JSON válido."
)
REF_IN_TEXT = re.compile(r"\d+\s*[:.]\s*\d+")
REUSE_REF_DAYS = 180


def fingerprint(text: str) -> str:
    return hashlib.sha1(bible.normalize(text).encode()).hexdigest()[:12]


def _recent(used_section: dict, today: date, days: int) -> set[str]:
    limit = (today - timedelta(days=days)).isoformat()
    return {k for k, d in used_section.items() if d >= limit}


def _groq_verse(groq: GroqClient, avoid_refs: list[str]) -> dict:
    user = (
        "Escolha UM versículo bíblico curto e conhecido (1 a 3 versículos seguidos, no máximo "
        "300 caracteres) de encorajamento para o 'versículo do dia' e escreva uma reflexão.\n"
        f"Não use nenhuma destas referências: {', '.join(avoid_refs[:80]) or 'nenhuma'}.\n"
        "Não use o versículo 1 de Salmos (muitos têm título). Use nomes de livros em português.\n"
        "Responda neste formato JSON:\n"
        '{"ref": "Livro capítulo:versículo (ex.: Isaías 41:10 ou Salmos 37:4-5)", '
        '"theme": "tema em 1 ou 2 palavras", "mood": "reflexao ou alegria", '
        '"on_screen": "frase curta e marcante sobre o versículo, até 90 caracteres", '
        '"reflection": "reflexão de 2 a 3 frases, até 350 caracteres, sem citar outros versículos", '
        '"tags": ["duas", "hashtags sem # e sem acento"]}'
    )
    data = groq.chat_json(SYSTEM_PROMPT, user)
    item = {
        "id": f"g-{fingerprint(str(data.get('ref')))}",
        "ref": str(data.get("ref", "")),
        "theme": str(data.get("theme", ""))[:40],
        "mood": data.get("mood") if data.get("mood") in ("reflexao", "alegria") else "reflexao",
        "on_screen": str(data.get("on_screen", "")).strip(),
        "reflection": str(data.get("reflection", "")).strip(),
        "tags": [re.sub(r"[^a-z0-9]", "", bible.normalize(t)) for t in data.get("tags", [])][:3],
    }
    if REF_IN_TEXT.search(item["reflection"] + item["on_screen"]):
        raise validate.ContentError("a reflexão cita outra referência")
    if len(item["reflection"]) > 450:
        raise validate.ContentError("reflexão longa demais")
    ref = bible.parse_reference(item["ref"]) if item["ref"] else None
    if ref and ref.book == "PSA" and ref.verse_start == 1:
        raise validate.ContentError("Salmo versículo 1 (pode ter título)")
    return item


def _groq_quiz(groq: GroqClient, avoid_refs: list[str]) -> dict:
    user = (
        "Crie UMA pergunta de quiz bíblico no estilo 'Só 1% acerta', com 4 alternativas e "
        "UMA correta. A resposta correta deve ser uma palavra ou expressão curta que aparece "
        "LITERALMENTE no versículo indicado (nome, número por extenso, lugar ou objeto). "
        "As alternativas erradas devem ser plausíveis, mas NÃO podem aparecer no versículo.\n"
        f"Não use estas referências: {', '.join(avoid_refs[:80]) or 'nenhuma'}.\n"
        "Use nomes de livros em português. Pergunta com até 120 caracteres; alternativas com até 40.\n"
        "Responda neste formato JSON:\n"
        '{"question": "...", "options": ["A", "B", "C", "D"], "answer": 0, '
        '"ref": "Livro capítulo:versículo", "difficulty": "facil, medio ou dificil"}'
    )
    data = groq.chat_json(SYSTEM_PROMPT, user)
    options = [str(o).strip() for o in data.get("options", [])][:4]
    answer = data.get("answer")
    if isinstance(answer, str) and answer.strip().upper() in "ABCD" and len(answer.strip()) == 1:
        answer = "ABCD".index(answer.strip().upper())
    if not isinstance(answer, int) or not 0 <= answer < len(options):
        raise validate.ContentError("resposta inválida")
    return {
        "id": f"g-{fingerprint(str(data.get('question')))}",
        "question": str(data.get("question", "")).strip(),
        "options": options,
        "answer": answer,
        "ref": str(data.get("ref", "")),
        "evidence": options[answer],  # a própria resposta precisa estar no texto bíblico
        "difficulty": data.get("difficulty", "medio"),
    }


def _groq_curiosity(groq: GroqClient, avoid_refs: list[str]) -> dict:
    user = (
        "Escreva UMA curiosidade bíblica curta no estilo 'Você sabia?' (personagens, lugares, "
        "números, costumes da época), baseada em UM versículo específico, sem inventar nada além "
        "do que o versículo diz.\n"
        f"Não use estas referências: {', '.join(avoid_refs[:80]) or 'nenhuma'}.\n"
        "Use nomes de livros em português.\n"
        "Responda neste formato JSON:\n"
        '{"title": "título curto e chamativo, até 45 caracteres", '
        '"text": "explicação de 1 a 2 frases, até 220 caracteres", '
        '"ref": "Livro capítulo:versículo", '
        '"keyword": "nome, número por extenso ou palavra-chave que aparece LITERALMENTE no versículo", '
        '"tags": ["duas", "hashtags sem # e sem acento"]}'
    )
    data = groq.chat_json(SYSTEM_PROMPT, user)
    item = {
        "id": f"g-{fingerprint(str(data.get('title')))}",
        "title": str(data.get("title", "")).strip()[:60],
        "text": str(data.get("text", "")).strip(),
        "ref": str(data.get("ref", "")),
        "evidence": str(data.get("keyword", "")).strip(),
        "tags": [re.sub(r"[^a-z0-9]", "", bible.normalize(t)) for t in data.get("tags", [])][:3],
    }
    if len(item["text"]) > 300 or REF_IN_TEXT.search(item["text"] + item["title"]):
        raise validate.ContentError("curiosidade longa demais ou citando outra referência")
    return item


GROQ_GENERATORS = {"verse": _groq_verse, "quiz": _groq_quiz, "curiosity": _groq_curiosity}


def bank_status(kind: str, today: date, used: dict,
                log: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """(banco válido, itens ainda não usados): a mesma regra vale para pick e para a saturação."""
    used_ids = used.get(kind, {})
    recent_refs = _recent(used.get("refs", {}), today, REUSE_REF_DAYS)
    bank = []
    for item in validate.load_bank(kind):
        try:
            bank.append(validate.validate(kind, item))
        except validate.ContentError as exc:
            if log is not None:
                log.append(f"banco {item.get('id')} ignorado: {exc}")
    fresh = [i for i in bank if i["id"] not in used_ids and i["ref_key"] not in recent_refs]
    return bank, fresh


def pick(kind: str, today: date, used: dict, groq: GroqClient, settings: dict,
         rng: random.Random, log: list[str]) -> tuple[dict, dict]:
    """Devolve (conteúdo validado, atualizações para used.json)."""
    used_ids = used.get(kind, {})
    recent_refs = _recent(used.get("refs", {}), today, REUSE_REF_DAYS)
    used_fps = set(used.get("fingerprints", {}))
    stamp = today.isoformat()
    bank, fresh = bank_status(kind, today, used, log)

    ratio = float(settings.get("groq", {}).get("new_content_ratio", 0.3))
    want_new = groq.available() and (not fresh or rng.random() < ratio)
    if want_new:
        avoid = sorted({bible.parse_reference(i["ref"]).label for i in bank}
                       | {_label_from_key(k) for k in recent_refs})
        for attempt in range(2):
            try:
                raw = GROQ_GENERATORS[kind](groq, avoid)
                item = validate.validate(kind, raw)
                fp = fingerprint(item.get("question") or item.get("title") or item["ref_key"])
                if item["ref_key"] in recent_refs or fp in used_fps:
                    raise validate.ContentError("conteúdo repetido")
                item["source"] = "groq"
                item["model"] = groq.last_model
                log.append(f"{kind}: conteúdo novo da Groq ({groq.last_model}) aceito")
                return item, {"refs": {item["ref_key"]: stamp}, "fingerprints": {fp: stamp}}
            except (GroqUnavailable, validate.ContentError, bible.BibleError,
                    ValueError, TypeError, AttributeError, KeyError) as exc:
                log.append(f"{kind}: Groq tentativa {attempt + 1} descartada: {exc}")
                if isinstance(exc, GroqUnavailable):
                    break

    if fresh:
        item = rng.choice(fresh)
    else:
        # banco esgotado e Groq indisponível: reaproveita o usado há mais tempo
        item = min(bank, key=lambda i: used_ids.get(i["id"], ""))
        log.append(f"{kind}: banco esgotado, reaproveitando {item['id']}")
    item = {**item, "source": "bank"}
    updates = {kind: {item["id"]: stamp}, "refs": {item["ref_key"]: stamp}}
    if item.get("question") or item.get("title"):
        updates["fingerprints"] = {fingerprint(item.get("question") or item["title"]): stamp}
    return item, updates


def _label_from_key(key: str) -> str:
    book, chapter, verses = key.split(".")
    start, end = verses.split("-")
    return bible.Reference(book, int(chapter), int(start), int(end)).label
