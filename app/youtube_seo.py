"""Títulos e palavras-chave do YouTube (Shorts e vídeo longo).

O que costuma funcionar no YouTube (e o que aplicamos aqui):
- título curto: até ~70 caracteres aparecem inteiros no celular; o resto é cortado;
- a palavra-chave que as pessoas buscam vem logo no começo ("Quiz Bíblico",
  "Complete o versículo", "Verdadeiro ou falso");
- a própria pergunta no título gera curiosidade (a pessoa quer saber a resposta),
  mas NUNCA a resposta;
- no máximo 1 emoji e nada de caixa alta no título inteiro (parece spam);
- o título combina com a capa: a capa grita a chamada, o título traz a pergunta.
"""
from __future__ import annotations

import random

MAX_VISIBLE = 70   # o que aparece sem corte no celular
MAX_TITLE = 100    # limite do YouTube
SHORTS_TAG = " #shorts"

DIFFICULTY = {"facil": "nível fácil", "medio": "nível médio", "dificil": "nível difícil 🔥"}
BASE_TAGS = ["quiz bíblico", "perguntas bíblicas", "bíblia", "desafio bíblico", "evangélico", "gospel",
             "jesus", "palavra de deus"]
KIND_TAGS = {
    "quiz": ["quiz da bíblia", "perguntas e respostas bíblicas", "teste seu conhecimento bíblico"],
    "truefalse": ["verdadeiro ou falso", "verdadeiro ou falso bíblico", "quiz bíblico"],
    "fill": ["complete o versículo", "versículos bíblicos", "versículo do dia"],
    "verse": ["versículo do dia", "palavra do dia", "mensagem de fé", "devocional"],
    "curiosity": ["curiosidades bíblicas", "você sabia", "fatos da bíblia"],
    "compilation": ["quiz bíblico difícil", "40 perguntas bíblicas", "quiz bíblico completo",
                    "perguntas bíblicas com respostas", "jogo bíblico"],
}


def _fits(text: str, limit: int = MAX_VISIBLE) -> bool:
    return len(text) <= limit


def _first_fit(options: list[str]) -> str:
    """Primeira opção que cabe inteira no celular; senão a mais curta."""
    for opt in options:
        if _fits(opt):
            return opt
    return min(options, key=len)


def short_title(kind: str, item: dict, rng: random.Random | None = None) -> str:
    """Título do Short (já com #shorts no fim)."""
    rng = rng or random.Random(0)
    q = (item.get("question") or "").strip()
    level = DIFFICULTY.get(item.get("difficulty", ""), "")
    if kind == "quiz":
        options = [f"Quiz Bíblico: {q}", f"{q} 🤔 Quiz Bíblico", q]
        generic = rng.choice(["Quiz Bíblico: só 1% acerta essa pergunta 🤔",
                              f"Quiz Bíblico ({level}): você acerta essa?" if level else
                              "Quiz Bíblico: você acerta essa?",
                              "Pergunta bíblica que quase ninguém acerta 🤔"])
        title = _first_fit(options) if _fits(q) else generic
    elif kind == "truefalse":
        claim = f"{q} {item.get('shown', '')}".strip()
        options = [f"Verdadeiro ou falso? {q}", f"Verdadeiro ou falso: {claim}"]
        title = _first_fit(options) if _fits(options[0]) else "Verdadeiro ou falso? Só 1% acerta essa da Bíblia"
    elif kind == "fill":
        ref = item.get("ref_label", "")
        title = _first_fit([f"Complete o versículo: {ref} 📖 Você sabe de cor?",
                            f"Complete o versículo: {ref} 📖", "Complete o versículo! 📖 Você sabe de cor?"])
    elif kind == "verse":
        title = _first_fit([f"{item.get('on_screen', '')} | {item.get('ref_label', '')}",
                            f"Versículo do dia: {item.get('ref_label', '')}"])
    elif kind == "curiosity":
        title = _first_fit([f"Você sabia? {item.get('title', '')}", "Curiosidade bíblica que pouca gente sabe"])
    else:
        title = q or "Quiz Bíblico"
    title = title.strip()
    if len(title) > MAX_TITLE - len(SHORTS_TAG):
        title = title[:MAX_TITLE - len(SHORTS_TAG) - 1].rsplit(" ", 1)[0] + "…"
    return title + SHORTS_TAG


def long_title(total_n: int, minutes: int) -> str:
    """Título do vídeo longo: palavra-chave + número + promessa (cabe em 70 caracteres)."""
    return f"QUIZ BÍBLICO: {total_n} perguntas (só 1% acerta todas!) | {minutes} min"


def tags(kind: str, item: dict | None = None) -> list[str]:
    """Palavras-chave do vídeo (campo "tags" da API; até 500 caracteres no total)."""
    out = list(dict.fromkeys(KIND_TAGS.get(kind, []) + BASE_TAGS
                             + [t for t in (item or {}).get("tags", []) if t]))
    book = ((item or {}).get("ref_label") or "").rsplit(" ", 1)[0]
    if book:
        out.append(book.lower())
    kept, total = [], 0
    for t in out:
        if total + len(t) + 1 > 480:
            break
        kept.append(t)
        total += len(t) + 1
    return kept
