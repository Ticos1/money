"""Bíblia local (Bíblia Portuguesa Mundial, domínio público) e validação de
referências.

Toda referência usada em um post (do banco ou da Groq) passa por aqui. Se o
livro/capítulo/versículo não existir, ou se o trecho citado como evidência não
estiver no texto, o conteúdo é descartado.
"""
from __future__ import annotations

import gzip
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BIBLE_PATH = Path(__file__).resolve().parents[1] / "data" / "bible" / "bpm.json.gz"
TRANSLATION_NAME = "Bíblia Portuguesa Mundial"
TRANSLATION_ABBR = "BPM"

# (código no arquivo, nome em português, apelidos aceitos)
BOOKS: list[tuple[str, str, tuple[str, ...]]] = [
    ("GEN", "Gênesis", ("gn", "gen")),
    ("EXO", "Êxodo", ("ex", "exo")),
    ("LEV", "Levítico", ("lv", "lev")),
    ("NUM", "Números", ("nm", "num")),
    ("DEU", "Deuteronômio", ("dt", "deut")),
    ("JOS", "Josué", ("js", "jos")),
    ("JDG", "Juízes", ("jz", "jui")),
    ("RUT", "Rute", ("rt",)),
    ("1SA", "1 Samuel", ("1sm", "1 sm", "i samuel")),
    ("2SA", "2 Samuel", ("2sm", "2 sm", "ii samuel")),
    ("1KI", "1 Reis", ("1rs", "1 rs", "i reis")),
    ("2KI", "2 Reis", ("2rs", "2 rs", "ii reis")),
    ("1CH", "1 Crônicas", ("1cr", "1 cr", "i cronicas")),
    ("2CH", "2 Crônicas", ("2cr", "2 cr", "ii cronicas")),
    ("EZR", "Esdras", ("ed", "esd")),
    ("NEH", "Neemias", ("ne", "nee")),
    ("EST", "Ester", ("et",)),
    ("JOB", "Jó", ("job",)),
    ("PSA", "Salmos", ("sl", "salmo", "sal")),
    ("PRO", "Provérbios", ("pv", "prov")),
    ("ECC", "Eclesiastes", ("ec", "ecl")),
    ("SOL", "Cânticos", ("ct", "cantares", "cantico dos canticos", "canticos dos canticos", "cantares de salomao")),
    ("ISA", "Isaías", ("is",)),
    ("JER", "Jeremias", ("jr", "jer")),
    ("LAM", "Lamentações", ("lm", "lam")),
    ("EZE", "Ezequiel", ("ez", "eze")),
    ("DAN", "Daniel", ("dn", "dan")),
    ("HOS", "Oseias", ("os", "oseias")),
    ("JOE", "Joel", ("jl",)),
    ("AMO", "Amós", ("am",)),
    ("OBA", "Obadias", ("ob",)),
    ("JON", "Jonas", ("jn",)),
    ("MIC", "Miqueias", ("mq", "miqueias")),
    ("NAH", "Naum", ("na",)),
    ("HAB", "Habacuque", ("hc", "hab")),
    ("ZEP", "Sofonias", ("sf",)),
    ("HAG", "Ageu", ("ag",)),
    ("ZEC", "Zacarias", ("zc", "zac")),
    ("MAL", "Malaquias", ("ml", "mal")),
    ("MAT", "Mateus", ("mt",)),
    ("MAR", "Marcos", ("mc",)),
    ("LUK", "Lucas", ("lc",)),
    ("JOH", "João", ("jo",)),
    ("ACT", "Atos", ("at", "atos dos apostolos")),
    ("ROM", "Romanos", ("rm", "rom")),
    ("1CO", "1 Coríntios", ("1co", "1 co", "i corintios")),
    ("2CO", "2 Coríntios", ("2co", "2 co", "ii corintios")),
    ("GAL", "Gálatas", ("gl", "gal")),
    ("EPH", "Efésios", ("ef", "efe")),
    ("PHI", "Filipenses", ("fp", "fil")),
    ("COL", "Colossenses", ("cl", "col")),
    ("1TH", "1 Tessalonicenses", ("1ts", "1 ts", "i tessalonicenses")),
    ("2TH", "2 Tessalonicenses", ("2ts", "2 ts", "ii tessalonicenses")),
    ("1TI", "1 Timóteo", ("1tm", "1 tm", "i timoteo")),
    ("2TI", "2 Timóteo", ("2tm", "2 tm", "ii timoteo")),
    ("TIT", "Tito", ("tt",)),
    ("PHM", "Filemom", ("fm", "filemon")),
    ("HEB", "Hebreus", ("hb", "heb")),
    ("JAM", "Tiago", ("tg",)),
    ("1PE", "1 Pedro", ("1pe", "1 pe", "i pedro")),
    ("2PE", "2 Pedro", ("2pe", "2 pe", "ii pedro")),
    ("1JO", "1 João", ("1jo", "1 jo", "i joao")),
    ("2JO", "2 João", ("2jo", "2 jo", "ii joao")),
    ("3JO", "3 João", ("3jo", "3 jo", "iii joao")),
    ("JUD", "Judas", ("jd",)),
    ("REV", "Apocalipse", ("ap", "apoc")),
]

BOOK_NAMES = {code: name for code, name, _ in BOOKS}


def normalize(text: str) -> str:
    """minúsculas, sem acentos, sem pontuação, espaços simples."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _alias_table() -> dict[str, str]:
    table: dict[str, str] = {}
    for code, name, aliases in BOOKS:
        for alias in (name, *aliases):
            key = normalize(alias)
            table[key] = code
            table[key.replace(" ", "")] = code
    return table


ALIASES = _alias_table()
REF_RE = re.compile(r"^\s*(.+?)\s+(\d+)\s*[:.]\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*$")


@dataclass(frozen=True)
class Reference:
    book: str  # código, ex.: "JOH"
    chapter: int
    verse_start: int
    verse_end: int

    @property
    def label(self) -> str:
        """Ex.: 'João 3:16' ou '1 Coríntios 13:4-7'."""
        base = f"{BOOK_NAMES[self.book]} {self.chapter}:{self.verse_start}"
        return base if self.verse_end == self.verse_start else f"{base}-{self.verse_end}"

    @property
    def key(self) -> str:
        return f"{self.book}.{self.chapter}.{self.verse_start}-{self.verse_end}"


class BibleError(ValueError):
    pass


# Defesa extra: se algum versículo ainda tiver sinais de texto que não é bíblico
# (restos de tradução automática), ele nunca é publicado.
SUSPICIOUS = re.compile(r"USFM|```|diretrizes|Aqui está a tradução|português brasileiro", re.I)


@lru_cache(maxsize=1)
def _data() -> dict[str, dict[str, list[str]]]:
    with gzip.open(BIBLE_PATH, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def parse_reference(ref: str) -> Reference:
    m = REF_RE.match(ref or "")
    if not m:
        raise BibleError(f"Referência em formato inválido: {ref!r}")
    book_raw, ch, v1, v2 = m.groups()
    book_key = normalize(book_raw)
    # "Jó" e "Jo" (João) ficam iguais sem acento: o acento decide.
    if re.fullmatch(r"\s*j[óÓ]\s*", book_raw.lower()):
        code = "JOB"
    else:
        code = ALIASES.get(book_key) or ALIASES.get(book_key.replace(" ", ""))
    if not code:
        raise BibleError(f"Livro desconhecido: {book_raw!r}")
    start = int(v1)
    end = int(v2) if v2 else start
    if end < start or end - start > 12:
        raise BibleError(f"Intervalo de versículos inválido: {ref!r}")
    reference = Reference(code, int(ch), start, end)
    get_text(reference)  # valida existência
    return reference


def get_verses(reference: Reference) -> list[str]:
    chapter = _data().get(reference.book, {}).get(str(reference.chapter))
    if not chapter:
        raise BibleError(f"Capítulo inexistente: {reference.label}")
    if reference.verse_end > len(chapter):
        raise BibleError(f"Versículo inexistente: {reference.label}")
    verses = chapter[reference.verse_start - 1 : reference.verse_end]
    if any(not v for v in verses):
        raise BibleError(f"Versículo vazio nesta tradução: {reference.label}")
    if any(SUSPICIOUS.search(v) for v in verses):
        raise BibleError(f"Versículo com texto suspeito (revisar fonte): {reference.label}")
    return verses


def get_text(reference: Reference) -> str:
    return " ".join(get_verses(reference))


def display_text(reference: Reference, skip_prefix: str = "") -> str:
    """Texto pronto para exibir: sem título de salmo (skip_prefix), sem aspas
    soltas, começando com maiúscula e terminando com pontuação final."""
    text = get_text(reference)
    if skip_prefix:
        if not text.startswith(skip_prefix):
            raise BibleError(f"skip_prefix não confere em {reference.label}: {skip_prefix!r}")
        text = text[len(skip_prefix):].lstrip()
    for open_q, close_q in (("“", "”"), ("‘", "’")):
        if text.count(open_q) != text.count(close_q):
            text = text.replace(open_q, "").replace(close_q, "")
    text = text.strip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    if text and text[-1] in ",;:":
        text = text[:-1] + "…"
    elif text and text[-1] not in ".!?…":
        text += "."
    return text


_UNITS = ["zero", "um", "dois", "tres", "quatro", "cinco", "seis", "sete", "oito", "nove",
          "dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete",
          "dezoito", "dezenove"]
_TENS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_HUNDREDS = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos",
             "setecentos", "oitocentos", "novecentos"]


def number_to_words(n: int) -> str:
    """Números de 0 a 999 por extenso (sem acento), para comparar com o texto."""
    if n < 20:
        return _UNITS[n]
    if n < 100:
        t, u = divmod(n, 10)
        return _TENS[t] + (f" e {_UNITS[u]}" if u else "")
    if n == 100:
        return "cem"
    if n < 1000:
        h, rest = divmod(n, 100)
        return _HUNDREDS[h] + (f" e {number_to_words(rest)}" if rest else "")
    return str(n)


STOPWORDS = {"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na",
             "nos", "nas", "um", "uma", "uns", "umas", "por", "para", "com", "que", "ao", "aos",
             "seu", "sua", "seus", "suas", "ele", "ela", "foi", "era", "se"}


def _numbers_as_words(text: str) -> str:
    return re.sub(r"\d+", lambda m: number_to_words(int(m.group())), text)


def contains_phrase(passage: str, phrase: str) -> bool:
    """O trecho (sem acento/pontuação, números por extenso) está no texto?"""
    hay = f" {normalize(_numbers_as_words(passage))} "
    needle = normalize(_numbers_as_words(phrase))
    return bool(needle) and f" {needle} " in hay


def answer_supported(passage: str, answer: str) -> bool:
    """Todas as palavras relevantes da resposta aparecem no texto bíblico?"""
    hay = set(normalize(_numbers_as_words(passage)).split())
    words = [w for w in normalize(_numbers_as_words(answer)).split() if w not in STOPWORDS]
    return bool(words) and all(w in hay for w in words)
