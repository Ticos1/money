"""Formatos de vídeo montados a partir dos bancos que já existem (sem conteúdo inventado).

- "fill" (Complete o versículo): um versículo conhecido do banco com uma palavra-chave
  escondida; 4 opções; a certa é a palavra original do texto bíblico.
- "truefalse" (Verdadeiro ou falso?): uma pergunta do banco de quiz com uma resposta
  mostrada (a certa ou uma das erradas); o vídeo revela se era verdade.

Como tudo sai de itens já validados contra a Bíblia, não há risco de texto inventado.
"""
from __future__ import annotations

import random
import re
from datetime import date, timedelta

from . import bible, validate

KINDS = ("fill", "truefalse")
MAX_FILL_CHARS = 220
RECENT_DAYS = 120  # o mesmo item não volta neste formato por 120 dias

# palavras-chave que podem ser escondidas, separadas por gênero para as opções soarem naturais
FEM = ["paz", "fé", "graça", "luz", "força", "vida", "verdade", "esperança", "alegria", "justiça",
       "palavra", "salvação", "misericórdia", "rocha", "fortaleza", "glória", "alma", "sabedoria",
       "bondade", "fidelidade", "presença", "liberdade", "promessa"]
MASC = ["amor", "caminho", "coração", "pastor", "refúgio", "escudo", "descanso", "perdão", "reino",
        "nome", "medo", "mundo", "socorro", "poder", "fruto", "tesouro", "conselho", "louvor",
        "cântico", "auxílio", "Espírito", "temor"]
WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+")


def _recent(section: dict, today: date, days: int) -> set[str]:
    limit = (today - timedelta(days=days)).isoformat()
    return {k for k, d in section.items() if d >= limit}


def make_fill(item: dict, rng: random.Random) -> dict | None:
    """Esconde uma palavra-chave do versículo. None se o versículo não serve."""
    text = item["verse_text"]
    if len(text) > MAX_FILL_CHARS:
        return None
    present = {bible.normalize(w) for w in WORD.findall(text)}
    candidates = []
    for group in (FEM, MASC):
        for word in group:
            for m in WORD.finditer(text):
                if m.group().lower() == word.lower():
                    candidates.append((m, group))
                    break
    if not candidates:
        return None
    match, group = rng.choice(candidates)
    original = match.group()
    pool = [w for w in group if bible.normalize(w) not in present]
    if len(pool) < 3:
        return None
    distractors = rng.sample(pool, 3)
    if original[0].isupper():
        distractors = [d[0].upper() + d[1:] for d in distractors]
    options = [original] + distractors
    rng.shuffle(options)
    blanked = text[:match.start()] + "_____" + text[match.end():]
    return {**item, "blanked": blanked, "answer_word": original, "options": options,
            "answer": options.index(original), "question": blanked}


def make_truefalse(item: dict, rng: random.Random) -> dict:
    """Mostra a resposta certa ou uma errada (metade das vezes cada)."""
    correct = item["options"][item["answer"]]
    is_true = rng.random() < 0.5
    shown = correct if is_true else rng.choice([o for i, o in enumerate(item["options"]) if i != item["answer"]])
    return {**item, "shown": shown, "is_true": is_true, "correct": correct}


def _valid_bank(source: str) -> list[dict]:
    bank = []
    for raw in validate.load_bank(source):
        try:
            bank.append(validate.validate(source, dict(raw)))
        except (validate.ContentError, bible.BibleError):
            continue
    return bank


def fill_ready(item: dict) -> bool:
    """O versículo serve para 'Complete o versículo'? (tamanho e palavra-chave escondível)"""
    return make_fill(item, random.Random(0)) is not None


def bank_status(kind: str, today: date, used: dict) -> tuple[list[dict], list[dict]]:
    """(banco válido, itens que ainda não saíram neste formato): usado por pick e pela saturação."""
    seen = _recent(used.get(kind, {}), today, RECENT_DAYS)
    recent_refs = _recent(used.get("refs", {}), today, 3)  # não repete o versículo dos últimos dias
    if kind == "fill":
        bank = _valid_bank("verse")
        return bank, [i for i in bank if i["id"] not in seen and i["ref_key"] not in recent_refs]
    bank = _valid_bank("quiz")
    recent_quiz = _recent(used.get("quiz", {}), today, 60)
    return bank, [i for i in bank if i["id"] not in seen and i["id"] not in recent_quiz
                  and i["ref_key"] not in recent_refs]


def pick(kind: str, today: date, used: dict, groq, settings: dict, rng: random.Random,
         log: list[str]) -> tuple[dict, dict]:
    """Mesmo formato de content.pick: (conteúdo pronto, atualizações para used.json)."""
    stamp = today.isoformat()
    seen = used.get(kind, {})
    bank, fresh = bank_status(kind, today, used)
    if kind == "fill":
        rng.shuffle(fresh)
        for item in fresh + sorted(bank, key=lambda i: seen.get(i["id"], "")):
            built = make_fill(item, rng)
            if built:
                return {**built, "source": "bank"}, {kind: {item["id"]: stamp}}
        raise RuntimeError("nenhum versículo do banco serve para 'Complete o versículo'")

    item = rng.choice(fresh) if fresh else min(bank, key=lambda i: seen.get(i["id"], ""))
    if not fresh:
        log.append(f"{kind}: banco esgotado, reaproveitando {item['id']}")
    return ({**make_truefalse(item, rng), "source": "bank"},
            {kind: {item["id"]: stamp}, "quiz": {item["id"]: stamp}})
