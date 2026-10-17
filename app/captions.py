"""Legendas + hashtags adaptadas para cada rede.

Base: modelos fixos (sempre funcionam). Se a Groq estiver disponível, ela cria
variações de texto; a saída passa por checagens e, se reprovada, fica o modelo.
"""
from __future__ import annotations

import json
import os
import random
import re

from . import bible, config, keywords, youtube_seo
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
    "Pare um minuto e leia isto",
    "Esse versículo é para quem está cansado hoje",
    "Se você precisava de uma palavra, ela chegou",
]
VERSE_CTAS = [
    "Compartilhe com alguém que precisa ler isso hoje.",
    "Salve para ler de novo quando precisar.",
    "Envie para quem precisa ouvir isso hoje.",
]
QUIZ_HOOKS = [
    "Só 1% acerta essa pergunta da Bíblia!",
    "Você conhece mesmo a Bíblia? Prove!",
    "Pergunta bíblica que poucos acertam",
    "Desafio bíblico do dia",
    "Teste rápido: você acerta de primeira?",
    "Duvido você acertar sem pesquisar!",
    "Quem sabe de cabeça? Responda antes da contagem!",
]
CURIOSITY_HOOKS = [
    "Você sabia disso?",
    "Curiosidade bíblica que pouca gente conhece",
    "Isso está na Bíblia e muita gente não sabe",
    "Aprenda algo novo sobre a Bíblia hoje",
    "Poucos sabem disso sobre a Bíblia",
    "Essa você provavelmente nunca ouviu",
]
CURIOSITY_CTAS = [
    "Você já sabia? Comente SIM ou NÃO.",
    "Salve para lembrar e compartilhe com quem ama a Palavra.",
    "Compartilhe com quem vai gostar de saber disso.",
]
# formatos de pergunta: o mesmo pedido de comentário do vídeo ("Comente a letra"), sempre
LETTER_CTA = "Comente a letra: A, B, C ou D 👇"
FILL_CTAS = [LETTER_CTA]
TF_CTAS = ["Comente V ou F antes de ver a resposta 👇"]
BOOK_CTAS = [LETTER_CTA]
QUIZ_CTAS = [LETTER_CTA]


def _hashtags(kind: str, item: dict, platform: str, rng: random.Random) -> str:
    cfg = json.loads((CONTENT_DIR / "hashtags.json").read_text(encoding="utf-8"))
    limit = cfg["platform_limits"][platform]
    # tema de busca primeiro (#versiculoparaansiedade), depois as tags do próprio conteúdo
    own = list(dict.fromkeys(keywords.hashtags(kind, item) + [t for t in item.get("tags", []) if t]))
    pool = list(dict.fromkeys(own + cfg[kind] + cfg["base"]))
    head, tail = pool[: len(own) + 2], pool[len(own) + 2:]
    rng.shuffle(tail)
    tags = (head + tail)[:limit]
    if platform == "youtube":
        tags = ["shorts"] + tags[: limit - 1]
    return " ".join(f"#{t}" for t in tags)


FILL_HOOKS = [
    "Complete o versículo! 90% erra essa palavra",
    "Qual palavra falta nesse versículo?",
    "Você sabe esse versículo de cor?",
    "Desafio: complete o versículo sem olhar a Bíblia!",
]
TF_HOOKS = [
    "Verdadeiro ou falso? Só 1% acerta de primeira!",
    "Verdade ou mentira? Teste o seu conhecimento bíblico",
    "Verdadeiro ou falso: você acerta essa?",
]
BOOK_HOOKS = [
    "Em qual livro da Bíblia está este versículo?",
    "Você sabe de onde é este versículo?",
    "Desafio: descubra o livro deste versículo!",
    "Só 1% acerta o livro deste versículo",
]


AI_HOOK = "Legenda da IA"  # a Groq escreve a abertura inteira: entra no teste como um gancho só
CAROUSEL_LINE = "➡️ Arraste para o lado: tem uma aplicação prática para hoje."


def hook_label(caps: dict, caption_source: str | None) -> str | None:
    """Qual gancho abriu a legenda (teste A/B de ganchos). Serve também para posts antigos,
    gravados antes de o gancho ser registrado: é deduzido do começo da legenda."""
    if caption_source == "groq":
        return AI_HOOK
    text = (caps or {}).get("instagram") or (caps or {}).get("facebook") or ""
    if not isinstance(text, str):
        return None
    hooks = sorted(VERSE_HOOKS + QUIZ_HOOKS + CURIOSITY_HOOKS + FILL_HOOKS + TF_HOOKS + BOOK_HOOKS,
                   key=len, reverse=True)
    # antes do gancho podem vir a saudação de data especial e a palavra-chave de busca
    # ("Versículo para ansiedade: …"), cada uma na sua linha
    lines = [line for line in text.split("\n") if line.strip()]
    starts = ["\n".join(lines[i:]) for i in range(min(3, len(lines)))]
    return next((h for h in hooks if any(t.startswith(h) for t in starts)), None)


def hook_of(post: dict) -> str | None:
    return post.get("hook") or hook_label(post.get("captions") or {}, post.get("caption_source"))


def template_captions(kind: str, item: dict, handle: str, rng: random.Random) -> dict:
    if kind == "fill":
        hook = rng.choice(FILL_HOOKS)
        cta = rng.choice(FILL_CTAS)
        letters = "\n".join(f"{'ABCD'[i]}) {o}" for i, o in enumerate(item["options"]))
        long_text = (f"{hook} 📖\n\n“{item['question']}”\n\n{letters}\n\n{cta}\n"
                     "A resposta está no final do vídeo.")
        return {"hook": hook, "long": long_text, "short": f"{hook} 📖\n{cta}",
                "youtube_title": f"{hook} ({item['ref_label']})", "cta": cta}
    if kind == "book":
        hook = rng.choice(BOOK_HOOKS)
        cta = rng.choice(BOOK_CTAS)
        letters = "\n".join(f"{'ABCD'[i]}) {o}" for i, o in enumerate(item["options"]))
        long_text = (f"{hook} 📖\n\n{item['question']}\n\n{letters}\n\n{cta}\n"
                     "A resposta está no final do vídeo.")
        return {"hook": hook, "long": long_text, "short": f"{hook} 📖\n{cta}",
                "youtube_title": hook,
                "cta": cta}
    if kind == "truefalse":
        hook = rng.choice(TF_HOOKS)
        cta = rng.choice(TF_CTAS)
        long_text = (f"{hook} 🤔\n\n{item['question']}\nResposta: {item['shown']}\n\n"
                     f"Verdadeiro ou falso? {cta}\nA resposta está no final do vídeo.")
        return {"hook": hook, "long": long_text, "short": f"{hook} 🤔\n{cta}",
                "youtube_title": f"Verdadeiro ou falso? {item['question']}", "cta": cta}
    if kind == "verse":
        hook = rng.choice(VERSE_HOOKS)
        cta = rng.choice(VERSE_CTAS)
        quote = f"“{item['verse_text']}” ({item['ref_label']})"
        long_text = f"{hook} 🙏\n\n{quote}\n\n{item['reflection']}\n\n{cta}"
        short_text = f"{hook} 🙏 {item['ref_label']}\n{cta}"
        yt_title = f"{item['ref_label']}: {item['on_screen']}"
    elif kind == "curiosity":
        hook = rng.choice(CURIOSITY_HOOKS)
        cta = rng.choice(CURIOSITY_CTAS)
        long_text = f"{hook} 📖\n\n{item['title']}\n\n{item['text']} ({item['ref_label']})\n\n{cta}"
        short_text = f"{hook} 📖 {item['title']}\n{cta}"
        yt_title = f"Você sabia? {item['title']}"
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


# Canal do WhatsApp: ninguém comenta (só reage) e hashtag não serve para nada.
WHATSAPP_CTAS = {
    "verse": "Reaja com 🙏 se você recebe essa palavra e encaminhe para quem precisa ler isso hoje.",
    "curiosity": "Reaja com 😮 se você não sabia e encaminhe para quem ama a Palavra.",
}
WHATSAPP_QUIZ_CTA = "Reaja com ✅ se você acertou e encaminhe para desafiar alguém!"


def _site_url() -> str:
    """Endereço do mini-site (/hoje/), se o workflow informou um válido."""
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    return f"{base}/hoje/" if base.startswith("https://") and "://." not in base else ""


def whatsapp_caption(kind: str, texts: dict) -> str:
    body = texts["long"].replace(" (ou arraste para o lado no carrossel)", "")
    if texts.get("cta"):
        body = body.replace(texts["cta"], "")
    for line in (LETTER_CTA, *TF_CTAS):
        body = body.replace(line, "")
    body = re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", body)).strip()
    hook = texts.get("hook", "")
    if hook and body.startswith(hook):  # negrito do WhatsApp na abertura
        body = f"*{hook}*{body[len(hook):]}"
    parts = [body, WHATSAPP_CTAS.get(kind, WHATSAPP_QUIZ_CTA)]
    site = _site_url()
    if site:
        parts.append(f"🎯 Quiz de hoje com placar: {site}" if kind != "verse"
                     else f"📖 Versículo e quiz de hoje: {site}")
    parts.append(ATTRIBUTION)
    return "\n\n".join(parts)


def _assemble(kind: str, item: dict, texts: dict, handle: str, rng: random.Random,
              carousel: bool = False) -> dict:
    tag = lambda p: _hashtags(kind, item, p, rng)  # noqa: E731
    follow = f"Siga {handle} para mais." if handle else ""
    swipe = f"\n\n{CAROUSEL_LINE}" if carousel else ""
    yt_title = youtube_seo.short_title(kind, item, rng)  # curto, palavra-chave na frente, sem a resposta
    # busca: "Versículo para ansiedade: Filipenses 4:6" na 1ª linha (o WhatsApp não tem busca)
    key = keywords.first_line(kind, item)
    top = f"{key}\n" if key else ""
    phrase = keywords.search_phrase(kind, item)  # legenda curta já traz a referência
    top_short = f"{phrase}\n" if phrase else ""
    return {
        "instagram": f"{top}{texts['long']}{swipe}\n\n{follow}\n{ATTRIBUTION}\n\n{tag('instagram')}".strip(),
        "facebook": f"{top}{texts['long']}\n\n{follow}\n{ATTRIBUTION}\n\n{tag('facebook')}".strip(),
        "tiktok": f"{top_short}{texts['short']}\n{tag('tiktok')}",
        "kwai": f"{top_short}{texts['short']}\n{tag('kwai')}",
        "whatsapp": whatsapp_caption(kind, texts),
        "youtube": {
            "title": yt_title,
            "description": f"{top}{texts['long']}\n\n{follow}\n{ATTRIBUTION}\n\n{tag('youtube')}",
            "tags": youtube_seo.tags(kind, item),
        },
    }


def _groq_texts(kind: str, item: dict, groq: GroqClient, base: dict) -> dict:
    if kind == "verse":
        about = (f"Versículo do dia: {item['ref_label']} — “{item['verse_text']}”. "
                 f"Reflexão: {item['reflection']}")
        rules = "NÃO escreva o texto do versículo (ele é adicionado automaticamente, exato)."
    elif kind == "curiosity":
        about = f"Curiosidade bíblica: {item['title']}. {item['text']} ({item['ref_label']})"
        rules = "Não invente fatos novos além da curiosidade informada."
    else:
        about = f"Quiz bíblico. Pergunta: {item['question']} Alternativas: {item['options']}"
        rules = "NÃO revele nem dê pistas da resposta certa."
    user = (
        f"Escreva variações de legenda para redes sociais sobre este post. {about}\n"
        f"Regras: {rules} Não cite outros versículos ou referências bíblicas. Não use hashtags. "
        "Não peça para digitar ou comentar palavras (ex.: AMÉM) nem para marcar pessoas; "
        "se quiser uma chamada, peça para salvar ou compartilhar. "
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
    elif kind == "curiosity":
        # o texto da curiosidade (já validado na Bíblia) sempre vai junto
        texts["long"] = f"{item['title']}\n\n{item['text']} ({item['ref_label']})\n\n{texts['long']}"
    else:
        letters = "\n".join(f"{'ABCD'[i]}) {o}" for i, o in enumerate(item["options"]))
        texts["long"] = f"{texts['long']}\n\n{item['question']}\n{letters}\n\n{base['cta']}"
        texts["short"] = f"{texts['short']}\n{base['cta']}"
    texts["cta"] = base["cta"]
    return texts


def build(kind: str, item: dict, settings: dict, groq: GroqClient, rng: random.Random,
          log: list[str]) -> tuple[dict, str]:
    """Devolve (legendas por plataforma, origem: 'template' ou 'groq')."""
    handle = settings.get("brand", {}).get("handle", "")
    texts = template_captions(kind, item, handle, rng)
    source = "template"
    # formatos com resposta escondida usam só o modelo fixo (a IA poderia entregar a resposta)
    if kind in ("verse", "quiz", "curiosity") and settings.get("groq", {}).get("caption_variations", True) \
            and groq.available():
        try:
            texts = _groq_texts(kind, item, groq, texts)
            source = "groq"
        except (GroqUnavailable, ValueError, TypeError, AttributeError, KeyError) as exc:
            log.append(f"legenda Groq descartada: {exc}")
    if item.get("date_hook"):  # data especial (Natal, Páscoa...): saudação no começo
        hook = item["date_hook"]
        texts = {**texts, "long": f"{hook}\n\n{texts['long']}", "short": f"{hook}\n{texts['short']}"}
    carousel = kind == "verse" and config.verse_carousel(settings)
    return _assemble(kind, item, texts, handle, rng, carousel), source
