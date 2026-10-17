"""Palavra-chave de busca a partir do tema do conteúdo (campo `theme` do banco de versículos).

Quem procura "versículo para ansiedade" no Instagram, TikTok ou YouTube chega por
palavra-chave. Por isso o tema vira uma frase de busca que entra:
- na primeira linha da legenda (é o trecho que as redes mais leem na busca);
- no começo do título do YouTube;
- nas hashtags e nas tags do vídeo.

Só temas da lista abaixo viram frase de busca: a lista usa o jeito que as pessoas
escrevem na busca ("versículo para ansiedade", "versículo de esperança"). Tema fora
da lista (ex.: um tema novo escrito pela IA) simplesmente não ganha a linha.
"""
from __future__ import annotations

from . import bible

_PHRASES = {
    "Versículo para ansiedade": ["ansiedade", "preocupação", "preocupações"],
    "Versículo contra o medo": ["medo", "temor"],
    "Versículo para a família": ["família", "lar", "casamento", "filhos"],
    "Versículo para o trabalho": ["trabalho", "serviço"],
    "Versículo de esperança": ["esperança", "esperança eterna", "futuro"],
    "Versículo sobre oração": ["oração"],
    "Versículo sobre amor": ["amor"],
    "Versículo sobre o amor de Deus": ["amor de Deus"],
    "Versículo de paz": ["paz"],
    "Versículo de alegria": ["alegria", "alegria em Deus", "contentamento"],
    "Versículo sobre identidade em Cristo": ["identidade", "valor", "valor verdadeiro", "pertencimento"],
    "Versículo sobre salvação": ["salvação", "evangelho", "cruz"],
    "Versículo sobre a Palavra de Deus": ["Palavra de Deus", "Palavra"],
    "Versículo de coragem": ["coragem"],
    "Versículo sobre fé": ["fé"],
    "Versículo de louvor": ["louvor", "adoração"],
    "Versículo sobre a presença de Deus": ["presença de Deus", "presença", "intimidade", "vida com Deus"],
    "Versículo de força": ["força", "poder de Deus"],
    "Versículo de proteção": ["proteção", "refúgio", "segurança", "socorro"],
    "Versículo sobre perdão": ["perdão"],
    "Versículo de consolo": ["consolo", "encorajamento"],
    "Versículo para tomar decisões": ["direção", "decisão", "planos"],
    "Versículo sobre confiar em Deus": ["confiança", "entrega", "dependência"],
    "Versículo para não desistir": ["perseverança", "firmeza"],
    "Versículo para tempos difíceis": ["provação", "batalhas", "fardos", "impossível"],
    "Versículo sobre propósito": ["propósito", "missão", "dons"],
    "Versículo de descanso": ["descanso"],
    "Versículo sobre a fidelidade de Deus": ["fidelidade"],
    "Versículo sobre graça": ["graça"],
    "Versículo sobre sabedoria": ["sabedoria"],
    "Versículo de gratidão": ["gratidão"],
    "Versículo sobre misericórdia": ["misericórdia"],
    "Versículo sobre Jesus": ["Jesus"],
    "Versículo de vitória": ["vitória", "batalha espiritual"],
    "Versículo de bênção": ["bênção"],
    "Versículo de cura": ["cura"],
    "Versículo sobre liberdade": ["liberdade"],
    "Versículo para quem espera em Deus": ["espera", "tempo"],
    "Versículo sobre paciência": ["paciência"],
    "Versículo sobre humildade": ["humildade"],
    "Versículo sobre o cuidado de Deus": ["cuidado", "cuidado de Deus", "bondade de Deus"],
    "Versículo de provisão": ["provisão"],
    "Versículo sobre amizade": ["amizade"],
    "Versículo sobre amor ao próximo": ["amor ao próximo"],
    "Versículo de recomeço": ["recomeço", "renovo", "renovação", "nova vida", "vida nova", "transformação"],
    "Versículo sobre o Espírito Santo": ["Espírito Santo", "fruto do Espírito"],
    "Versículo sobre generosidade": ["generosidade"],
    "Versículo sobre arrependimento": ["arrependimento"],
    "Versículo sobre justiça": ["justiça"],
    "Versículo contra a tentação": ["tentação", "pureza"],
    "Versículo sobre obediência": ["obediência"],
    "Versículo sobre o poder das palavras": ["palavras"],
    "Versículo sobre a ressurreição": ["ressurreição"],
    "Versículo para jovens": ["juventude"],
    "Versículo sobre unidade": ["unidade", "união", "comunhão"],
}
SEARCH = {bible.normalize(theme): phrase for phrase, themes in _PHRASES.items() for theme in themes}
KINDS = ("verse", "fill")  # só os versículos têm tema no banco


def slug(text: str) -> str:
    return bible.normalize(text).replace(" ", "")


def search_phrase(kind: str, item: dict) -> str:
    """Frase de busca do post ("Versículo para ansiedade") ou "" se o tema não tem uma.
    No "Complete o versículo" a frase nunca pode conter a palavra escondida."""
    if kind not in KINDS:
        return ""
    phrase = SEARCH.get(bible.normalize(str(item.get("theme") or "")), "")
    if phrase and kind == "fill":
        hidden = bible.normalize(str(item.get("answer_word") or ""))
        if not hidden or hidden in bible.normalize(phrase).split():
            return ""
    return phrase


def first_line(kind: str, item: dict) -> str:
    """Primeira linha da legenda: "Versículo para ansiedade: Filipenses 4:6"."""
    phrase = search_phrase(kind, item)
    if not phrase:
        return ""
    ref = item.get("ref_label", "")
    return f"{phrase}: {ref}" if ref else phrase


def hashtags(kind: str, item: dict) -> list[str]:
    """#versiculoparaansiedade e #ansiedade (o tema sozinho, quando é uma palavra)."""
    phrase = search_phrase(kind, item)
    if not phrase:
        return []
    out = [slug(phrase)]
    theme = str(item.get("theme") or "").strip()
    if theme and " " not in theme:
        out.append(slug(theme))
    return out


def youtube_tags(kind: str, item: dict) -> list[str]:
    phrase = search_phrase(kind, item)
    if not phrase:
        return []
    low = phrase[0].lower() + phrase[1:]  # "versículo para ansiedade"
    theme = str(item.get("theme") or "").strip().lower()
    return [t for t in dict.fromkeys([low, "versículos" + low[len("versículo"):], theme]) if t]
