"""Escolha do conteúdo de cada post: banco local + complemento da Groq.

Ordem de decisão:
1. Às vezes (config groq.new_content_ratio) tenta gerar conteúdo NOVO na Groq.
   Ele só é aceito se passar na mesma validação bíblica do banco. Quiz e
   curiosidade partem de um capítulo sorteado (ainda não usado) da Bíblia local,
   enviado no prompt: a IA não repete os versículos famosos e a evidência existe.
2. Senão (ou se a Groq falhar), pega um item do banco ainda não usado.
3. Se o banco acabou e a Groq falhou, reutiliza o item usado há mais tempo,
   para o post do dia nunca deixar de sair.
"""
from __future__ import annotations

import hashlib
import random
import re
from datetime import date, timedelta

from . import bible, datas, validate
from .groq_client import GroqClient, GroqUnavailable

SYSTEM_PROMPT = (
    "Você é um redator cristão evangélico brasileiro. Escreve em português do Brasil, "
    "com tom respeitoso, acolhedor e fiel à Bíblia, sem polêmicas denominacionais, "
    "sem promessas de prosperidade e sem inventar fatos. Responda somente com JSON válido."
)
REF_IN_TEXT = re.compile(r"\d+\s*[:.]\s*\d+")
REUSE_REF_DAYS = 180
MAX_CHAPTER_CHARS = 4500  # capítulo vai inteiro no prompt: limita os tokens do plano grátis


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


def chapter_pool(avoid_chapters: set[tuple[str, int]]) -> list[tuple[str, int]]:
    """Capítulos da Bíblia local que ainda não foram usados e cabem no prompt."""
    return [(book, int(ch)) for book, chapters in bible._data().items()
            for ch, verses in chapters.items()
            if (book, int(ch)) not in avoid_chapters
            and 0 < sum(len(v) for v in verses) <= MAX_CHAPTER_CHARS]


def _chapter_prompt(book: str, chapter: int) -> str:
    verses = bible._data()[book][str(chapter)]
    lines = "\n".join(f"{n} {v}" for n, v in enumerate(verses, 1)
                      if v and not bible.SUSPICIOUS.search(v))
    return f"Capítulo {bible.BOOK_NAMES[book]} {chapter} (número do versículo no começo da linha):\n{lines}\n"


def _chapter_ref(data: dict, book: str, chapter: int) -> str:
    """Referência dentro do capítulo enviado: a IA devolve só o número do versículo."""
    verse = str(data.get("verse", "")).strip()
    if not re.fullmatch(r"\d+(?:\s*-\s*\d+)?", verse):
        raise validate.ContentError(f"versículo inválido: {verse!r}")
    return f"{bible.BOOK_NAMES[book]} {chapter}:{verse.replace(' ', '')}"


def _groq_quiz(groq: GroqClient, avoid_refs: list[str], chapter: tuple[str, int]) -> dict:
    book, ch = chapter
    user = (
        _chapter_prompt(book, ch)
        + "Com base SÓ nesse capítulo, crie UMA pergunta de quiz bíblico no estilo 'Só 1% acerta', "
        "com 4 alternativas e UMA correta, sobre um versículo específico dele. A resposta correta "
        "deve ser uma palavra ou expressão curta copiada LITERALMENTE desse versículo (nome, número "
        "por extenso, lugar ou objeto). As 3 alternativas erradas devem ser plausíveis, mas NÃO podem "
        "aparecer em nenhum lugar do capítulo.\n"
        "Pergunta com até 120 caracteres; alternativas com até 40.\n"
        "Responda neste formato JSON:\n"
        '{"question": "...", "options": ["A", "B", "C", "D"], "answer": 0, '
        '"verse": "número do versículo onde está a resposta", "difficulty": "facil, medio ou dificil"}'
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
        "ref": _chapter_ref(data, book, ch),
        "evidence": options[answer],  # a própria resposta precisa estar no texto bíblico
        "difficulty": data.get("difficulty", "medio"),
    }


def _groq_curiosity(groq: GroqClient, avoid_refs: list[str], chapter: tuple[str, int]) -> dict:
    book, ch = chapter
    user = (
        _chapter_prompt(book, ch)
        + "Com base SÓ nesse capítulo, escreva UMA curiosidade bíblica curta no estilo 'Você sabia?' "
        "(personagens, lugares, números, costumes da época) sobre um versículo específico dele, "
        "sem inventar nada além do que o texto diz.\n"
        "Responda neste formato JSON:\n"
        '{"title": "título curto e chamativo, até 45 caracteres", '
        '"text": "explicação de 1 a 2 frases, até 220 caracteres", '
        '"verse": "número do versículo da curiosidade", '
        '"keyword": "nome, número por extenso ou palavra-chave copiada LITERALMENTE desse versículo", '
        '"tags": ["duas", "hashtags sem # e sem acento"]}'
    )
    data = groq.chat_json(SYSTEM_PROMPT, user)
    item = {
        "id": f"g-{fingerprint(str(data.get('title')))}",
        "title": str(data.get("title", "")).strip()[:60],
        "text": str(data.get("text", "")).strip(),
        "ref": _chapter_ref(data, book, ch),
        "evidence": str(data.get("keyword", "")).strip(),
        "tags": [re.sub(r"[^a-z0-9]", "", bible.normalize(t)) for t in data.get("tags", [])][:3],
    }
    if len(item["text"]) > 300 or REF_IN_TEXT.search(item["text"] + item["title"]):
        raise validate.ContentError("curiosidade longa demais ou citando outra referência")
    return item


def application(item: dict, groq: GroqClient, log: list[str]) -> str:
    """Aplicação prática do slide 3 do carrossel. Vazio = o template usa uma frase fixa."""
    if not groq.available():
        return ""
    user = (
        f"Versículo: {item['ref_label']} — “{item['verse_text']}”. Reflexão: {item.get('reflection', '')}\n"
        "Escreva UMA aplicação prática para hoje, concreta e simples (uma ação que a pessoa pode fazer), "
        "em 1 ou 2 frases, até 180 caracteres, falando com 'você'. Não cite outros versículos nem "
        "referências, sem hashtags e sem emojis.\n"
        'Responda em JSON: {"application": "..."}'
    )
    try:
        text = " ".join(str(groq.chat_json(SYSTEM_PROMPT, user).get("application", "")).split())
        if not 30 <= len(text) <= 220 or "#" in text or REF_IN_TEXT.search(text):
            raise ValueError("aplicação fora do padrão")
        return text
    except (GroqUnavailable, ValueError, TypeError, AttributeError) as exc:
        log.append(f"aplicação do carrossel pela Groq descartada: {exc}")
        return ""


GROQ_GENERATORS = {"verse": _groq_verse, "quiz": _groq_quiz, "curiosity": _groq_curiosity}
CHAPTER_KINDS = ("quiz", "curiosity")  # geradores que recebem um capítulo sorteado


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

    fresh, date_theme = datas.prefer(kind, today, fresh)  # data especial: tema do dia primeiro
    if date_theme:
        log.append(f"{kind}: data especial ({date_theme.name}), conteúdo temático")
    ratio = float(settings.get("groq", {}).get("new_content_ratio", 0.3))
    want_new = groq.available() and not date_theme and (not fresh or rng.random() < ratio)
    if want_new:
        avoid = sorted({bible.parse_reference(i["ref"]).label for i in bank}
                       | {_label_from_key(k) for k in recent_refs})
        # capítulos já usados (banco ou qualquer post anterior) não são sorteados de novo
        used_chapters = {(i["ref_key"].split(".")[0], int(i["ref_key"].split(".")[1])) for i in bank} \
            | {(k.split(".")[0], int(k.split(".")[1])) for k in used.get("refs", {})}
        chapters = chapter_pool(used_chapters) if kind in CHAPTER_KINDS else []
        for attempt in range(2):
            try:
                if kind in CHAPTER_KINDS:
                    if not chapters:
                        raise validate.ContentError("nenhum capítulo novo disponível")
                    chapter = chapters.pop(rng.randrange(len(chapters)))
                    raw = GROQ_GENERATORS[kind](groq, avoid, chapter)
                else:
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
    if date_theme:
        item["date_hook"] = date_theme.hook
    updates = {kind: {item["id"]: stamp}, "refs": {item["ref_key"]: stamp}}
    if item.get("question") or item.get("title"):
        updates["fingerprints"] = {fingerprint(item.get("question") or item["title"]): stamp}
    return item, updates


def _label_from_key(key: str) -> str:
    book, chapter, verses = key.split(".")
    start, end = verses.split("-")
    return bible.Reference(book, int(chapter), int(start), int(end)).label
