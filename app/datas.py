"""Calendário cristão: em datas especiais, prefere conteúdo do tema do dia.

Cada data tem `tags` (campo `tags` do item) e `themes` (campo `theme` do versículo) que
indicam conteúdo do banco combinando com ela. Se houver item novo (ainda não usado)
com o tema, ele é escolhido; senão o dia segue normal. Nada aqui inventa conteúdo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from . import bible


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    hook: str
    tags: frozenset[str]
    themes: frozenset[str] = field(default_factory=frozenset)
    kinds: tuple[str, ...] = ("verse", "quiz", "curiosity")


def easter(year: int) -> date:
    """Domingo de Páscoa (calendário gregoriano, algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def nth_sunday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def _t(key: str, name: str, hook: str, tags: set[str], themes: set[str] = frozenset(),
       kinds: tuple[str, ...] = ("verse", "quiz", "curiosity")) -> Theme:
    return Theme(key, name, hook, frozenset(tags), frozenset(themes), kinds)


NATAL = _t("natal", "Natal", "Feliz Natal! 🎄 Jesus é o motivo da festa.", {"natal"})
ANO_NOVO = _t("anonovo", "Ano Novo", "Feliz Ano Novo! 🎆 Que seja um ano de recomeço com Deus.",
              {"anonovo"}, {"recomeço", "renovo"})
SEXTA_SANTA = _t("sextasanta", "Sexta-feira Santa", "Sexta-feira Santa: lembrando o amor que foi até a cruz. ✝️",
                 {"sextasanta"}, {"cruz"})
PASCOA = _t("pascoa", "Páscoa", "Feliz Páscoa! Ele vive! ✝️🌅", {"pascoa"}, {"ressurreição"})
PENTECOSTES = _t("pentecostes", "Pentecostes", "Hoje é Pentecostes: o dia em que o Espírito Santo desceu. 🕊️",
                 {"pentecostes", "espiritosanto"})
MAES = _t("maes", "Dia das Mães", "Feliz Dia das Mães! 💐", {"maes"})
PAIS = _t("pais", "Dia dos Pais", "Feliz Dia dos Pais! 💙", {"pais"})
CRIANCA = _t("crianca", "Dia das Crianças", "Feliz Dia das Crianças! 🧸", {"crianca"})
REFORMA = _t("reforma", "Dia da Reforma", "31 de outubro: só a graça, só a fé. 📖", {"reforma"})
BIBLIA = _t("biblia", "Dia da Bíblia", "Hoje é o Dia da Bíblia! 📖", {"biblia"}, {"Palavra de Deus", "Palavra"})
DOMINGO = _t("domingo", "Domingo", "Bom domingo! Dia de louvar e de estar com a família da fé. 🙌",
             {"domingo", "louvor", "igreja", "comunhao"}, {"louvor", "comunhão"}, ("verse",))


def theme_for(day: date) -> Theme | None:
    pascoa = easter(day.year)
    md = (day.month, day.day)
    if md in ((12, 24), (12, 25)):
        return NATAL
    if md in ((12, 31), (1, 1)):
        return ANO_NOVO
    if day == pascoa - timedelta(days=2):
        return SEXTA_SANTA
    if day == pascoa:
        return PASCOA
    if day == pascoa + timedelta(days=49):
        return PENTECOSTES
    if day == nth_sunday(day.year, 5, 2):
        return MAES
    if day == nth_sunday(day.year, 8, 2):
        return PAIS
    if md == (10, 12):
        return CRIANCA
    if md == (10, 31):
        return REFORMA
    if day == nth_sunday(day.year, 12, 2):
        return BIBLIA
    if day.weekday() == 6:
        return DOMINGO
    return None


def matches(theme: Theme, item: dict) -> bool:
    tags = {bible.normalize(t).replace(" ", "") for t in item.get("tags", [])}
    if tags & theme.tags:
        return True
    return item.get("theme") in theme.themes if theme.themes else False


def prefer(kind: str, day: date, fresh: list[dict]) -> tuple[list[dict], Theme | None]:
    """Se hoje é data especial e há itens novos do tema, devolve só eles."""
    theme = theme_for(day)
    if not theme or kind not in theme.kinds:
        return fresh, None
    themed = [i for i in fresh if matches(theme, i)]
    return (themed, theme) if themed else (fresh, None)
