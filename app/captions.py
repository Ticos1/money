"""Legendas + hashtags adaptadas para cada rede.

Base: modelos fixos (sempre funcionam). Se a Groq estiver disponível, ela cria
variações de texto; a saída passa por checagens e, se reprovada, fica o modelo.
"""
from __future__ import annotations

import json
import random
import re

from . import bible
from .config import CONTENT_DIR
from .groq_client import GroqClient, GroqUnavailable

ATTRIBUTION = f"Texto bíblico: {bible.TRANSLATION_NAME} (domínio público)."

VERSE_HOOKS = [
    "Uma palavra para o seu dia",
    "Leia com calma e receba",
    "Deus tem uma palavra pra você hoje",
    "Para guardar no coração",
    "Se esse versículo chegou até você, não é por acaso",
    "Comece o dia com a Palavra",
]
VERSE_CTAS = [
    "Digite AMÉM se você recebe essa palavra.",
    "Compartilhe com alguém que precisa ler isso hoje.",
    "Salve para ler de novo quando precisar.",
    "Marque alguém para abençoar o dia dessa pessoa.",
]
QUIZ_HOOKS = [
    "Só 1% acerta essa pergunta da Bíblia!",
    "Você conhece mesmo a Bíblia? Prove!",
    "Pergunta bíblica que poucos acertam",
    "Desafio bíblico do dia",
    "Teste rápido: você acerta de primeira?",
]
QUIZ_CTAS = [
    "Comente a letra antes de ver a resposta!",
    "Responda nos comentários e desafie um amigo.",
    "Comente sua resposta e marque quem você acha que acerta.",
]


def _hashtags(kind: str, item: dict, platform: str, rng: random.Random) -> str:
    cfg = json.loads((CONTENT_DIR / "hashtags.json").read_text(encoding="utf-8"))
    limit = cfg["platform_limits"][platform]
    own = [t for t in item.get("tags", []) if t]
    pool = list(dict.fromkeys(own + cfg[kind] + cfg["base"]))
    head, tail = pool[: len(own) + 2], pool[len(own) + 2:]
    rng.shuffle(tail)
    tags = (head + tail)[:limit]
    if platform == "youtube":
        tags = ["shorts"] + tags[: limit - 1]
    return " ".join(f"#{t}" for t in tags)


def template_captions(kind: str, item: dict, handle: str, rng: random.Random) -> dict:
    if kind == "verse":
        hook = rng.choice(VERSE_HOOKS)
        cta = rng.choice(VERSE_CTAS)
        quote = f"“{item['verse_text']}” ({item['ref_label']})"
        long_text = f"{hook} 🙏\n\n{quote}\n\n{item['reflection']}\n\n{cta}"
        short_text = f"{hook} 🙏 {item['ref_label']}\n{cta}"
        yt_title = f"{item['ref_label']}: {item['on_screen']}"
    else:
        hook = rng.choice(QUIZ_HOOKS)
        cta = rng.choice(QUIZ_CTAS)
        letters = "\n".join(f"{'ABCD'[i]}) {o}" for i, o in enumerate(item["options"]))
        long_text = (f"{hook} 🤔\n\n{item['question']}\n\n{letters}\n\n{cta}\n"
                     "A resposta está no final do vídeo (ou arraste para o lado no carrossel).")
        short_text = f"{hook} 🤔\n{cta}"
        yt_title = f"{hook} {item['question']}"
    return {
        "hook": hook,
        "long": long_text,
        "short": short_text,
        "youtube_title": yt_title,
        "cta": cta,
    }


def _assemble(kind: str, item: dict, texts: dict, handle: str, rng: random.Random) -> dict:
    tag = lambda p: _hashtags(kind, item, p, rng)  # noqa: E731
    follow = f"Siga {handle} para mais." if handle else ""
    yt_title = texts["youtube_title"]
    if len(yt_title) > 90:
        yt_title = yt_title[:87].rsplit(" ", 1)[0] + "…"
    return {
        "instagram": f"{texts['long']}\n\n{follow}\n{ATTRIBUTION}\n\n{tag('instagram')}".strip(),
        "facebook": f"{texts['long']}\n\n{follow}\n{ATTRIBUTION}\n\n{tag('facebook')}".strip(),
        "tiktok": f"{texts['short']}\n{tag('tiktok')}",
        "kwai": f"{texts['short']}\n{tag('kwai')}",
        "youtube": {
            "title": f"{yt_title} #shorts"[:100],
            "description": f"{texts['long']}\n\n{follow}\n{ATTRIBUTION}\n\n{tag('youtube')}",
        },
    }


def _groq_texts(kind: str, item: dict, groq: GroqClient, base: dict) -> dict:
    if kind == "verse":
        about = (f"Versículo do dia: {item['ref_label']} — “{item['verse_text']}”. "
                 f"Reflexão: {item['reflection']}")
        rules = "NÃO escreva o texto do versículo (ele é adicionado automaticamente, exato)."
    else:
        about = f"Quiz bíblico. Pergunta: {item['question']} Alternativas: {item['options']}"
        rules = "NÃO revele nem dê pistas da resposta certa."
    user = (
        f"Escreva variações de legenda para redes sociais sobre este post. {about}\n"
        f"Regras: {rules} Não cite outros versículos ou referências bíblicas. Não use hashtags. "
        "Tom respeitoso, acolhedor, linguagem simples. Pode usar até 2 emojis por texto.\n"
        "Responda em JSON: {\"hook\": \"frase de abertura até 70 caracteres\", "
        "\"long\": \"legenda para Instagram/Facebook, até 600 caracteres\", "
        "\"short\": \"legenda curta para TikTok/Kwai, até 150 caracteres\", "
        "\"youtube_title\": \"título até 80 caracteres\"}"
    )
    data = groq.chat_json(
        "Você escreve legendas cristãs para redes sociais em português do Brasil. Responda só JSON.",
        user,
        temperature=0.9,
    )
    texts = {k: str(data.get(k, "")).strip() for k in ("hook", "long", "short", "youtube_title")}
    if not all(texts.values()):
        raise ValueError("legenda incompleta")
    if len(texts["long"]) > 900 or len(texts["short"]) > 220:
        raise ValueError("legenda longa demais")
    joined = " ".join(texts.values())
    if "#" in joined:
        raise ValueError("legenda com hashtag")
    refs_found = re.findall(r"\d+\s*[:.]\s*\d+", joined)
    allowed = item["ref_label"].split(" ")[-1]
    if any(r.replace(" ", "") not in allowed for r in refs_found):
        raise ValueError("legenda cita outra referência")
    if kind == "quiz":
        answer = bible.normalize(item["options"][item["answer"]])
        if f" {answer} " in f" {bible.normalize(joined)} ":
            raise ValueError("legenda revela a resposta")
    if kind == "verse":
        # a legenda longa sempre leva o versículo exato da Bíblia local
        texts["long"] = f"“{item['verse_text']}” ({item['ref_label']})\n\n{texts['long']}"
    else:
        letters = "\n".join(f"{'ABCD'[i]}) {o}" for i, o in enumerate(item["options"]))
        texts["long"] = f"{texts['long']}\n\n{item['question']}\n{letters}"
    texts["cta"] = base["cta"]
    return texts


def build(kind: str, item: dict, settings: dict, groq: GroqClient, rng: random.Random,
          log: list[str]) -> tuple[dict, str]:
    """Devolve (legendas por plataforma, origem: 'template' ou 'groq')."""
    handle = settings.get("brand", {}).get("handle", "")
    texts = template_captions(kind, item, handle, rng)
    source = "template"
    if settings.get("groq", {}).get("caption_variations", True) and groq.available():
        try:
            texts = _groq_texts(kind, item, groq, texts)
            source = "groq"
        except (GroqUnavailable, ValueError) as exc:
            log.append(f"legenda Groq descartada: {exc}")
    return _assemble(kind, item, texts, handle, rng), source
