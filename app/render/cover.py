"""Capas (miniaturas) do YouTube com texto grande.

- Shorts (1080x1920): selo "QUIZ BÍBLICO", chamada gigante em 2 linhas com contorno
  (ex.: "SÓ 1% / ACERTA") e a pergunta num cartão branco. Tudo fica na faixa central,
  que é o que aparece no recorte do feed, da busca e da grade do canal.
- Vídeo longo (1280x720): número de perguntas enorme à esquerda, promessa em amarelo
  à direita e uma faixa com a duração. Funciona em tamanho de celular (texto legível
  mesmo com a miniatura pequena).

Regras de miniatura que seguimos: no máximo ~5 palavras grandes, contraste alto
(branco/amarelo com contorno escuro), nada importante perto das bordas nem no canto
inferior direito (onde o YouTube põe a duração).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from . import design

DARK = (20, 20, 32, 255)
STROKE = (12, 12, 20, 255)
SHORT_SIZE = (1080, 1920)
LONG_SIZE = (1280, 720)
SHORT_FILE = "capa_youtube.jpg"

# chamada gigante (2 linhas) por formato; o texto do meio vem do conteúdo
HEADLINES = {
    "quiz": ("SÓ 1%", "ACERTA"),
    "truefalse": ("VERDADE", "OU MENTIRA?"),
    "fill": ("COMPLETE", "O VERSÍCULO"),
    "curiosity": ("VOCÊ", "SABIA?"),
    "verse": ("PALAVRA", "PARA HOJE"),
}
DIFFICULTY = {"facil": "NÍVEL FÁCIL", "medio": "NÍVEL MÉDIO", "dificil": "NÍVEL DIFÍCIL"}


def _big(canvas: Image.Image, text: str, kind: str, max_w: int, start: int, cy: int, fill,
         stroke: int | None = None) -> int:
    """Uma linha de texto no maior tamanho que couber em max_w, com contorno grosso. Devolve a altura."""
    size = start
    while size > 40 and design.font(kind, size).getlength(text) > max_w:
        size -= 4
    fnt = design.font(kind, size)
    width = stroke if stroke is not None else max(4, size // 14)
    d = ImageDraw.Draw(canvas)
    d.text((canvas.width // 2, cy + size // 18), text, font=fnt, fill=(0, 0, 0, 170), anchor="mm",
           stroke_width=width + 2, stroke_fill=(0, 0, 0, 170))
    d.text((canvas.width // 2, cy), text, font=fnt, fill=fill, anchor="mm", stroke_width=width,
           stroke_fill=STROKE)
    return size


def _pill(canvas: Image.Image, text: str, cx: int, cy: int, size: int, bg, fg=DARK) -> None:
    fnt = design.font("sans_black", size)
    tw = fnt.getlength(text)
    pad_x, pad_y = size * 0.9, size * 0.5
    box = (int(cx - tw / 2 - pad_x), int(cy - size / 2 - pad_y), int(cx + tw / 2 + pad_x), int(cy + size / 2 + pad_y))
    design.rounded_card(canvas, box, (box[3] - box[1]) // 2, bg + (255,))
    ImageDraw.Draw(canvas).text((cx, cy), text, font=fnt, fill=fg, anchor="mm")


def teaser(kind: str, item: dict) -> str:
    """Texto do cartão do meio: a própria pergunta (é ela que faz a pessoa parar)."""
    if kind == "fill":
        return f"{item.get('question', '')}"
    if kind == "truefalse":
        return f"{item.get('question', '')}\n→ {item.get('shown', '')}"
    if kind == "verse":
        return item.get("on_screen", "")
    if kind == "curiosity":
        return item.get("title", "")
    return item.get("question", "")


def _fit_lines(text: str, max_w: int):
    """Como design.fit, mas respeita quebras de linha do texto (usado no Verdadeiro ou falso)."""
    for size in range(74, 44, -2):
        fnt = design.font("sans_bold", size)
        lines = [ln for part in text.split("\n") for ln in design.wrap(part, fnt, max_w)]
        lh = int(size * 1.18)
        if len(lines) * lh <= 470:
            break
    return fnt, lines, lh


def short_cover(kind: str, item: dict, seed: int, handle: str, out: Path) -> None:
    w, h = SHORT_SIZE
    pal = design.palette_for("reflexao" if kind in ("fill", "verse") else "desafio", seed)
    img = design.background(w, h, pal, seed)
    img.alpha_composite(design.bokeh(w, h, pal, seed + 1, count=16))
    accent = pal.accent + (255,)

    _pill(img, "QUIZ BÍBLICO" if kind != "verse" else "VERSÍCULO DO DIA", w // 2, 330, 46, pal.accent)
    top, bottom = HEADLINES.get(kind, HEADLINES["quiz"])
    s1 = _big(img, top, "sans_black", 980, 260, 530, accent)
    _big(img, bottom, "sans_black", 980, min(200, s1), 530 + int(s1 * 0.95), (255, 255, 255, 255))

    # cartão com a pergunta (texto grande; corta com reticências se não couber)
    text = teaser(kind, item).strip()
    x0, x1, top_y = 80, w - 80, 900
    pad = 50
    fnt, lines, lh = _fit_lines(text, x1 - x0 - 2 * pad)
    if len(lines) * lh > 470:
        keep = max(1, 470 // lh)
        lines = lines[:keep]
        lines[-1] = lines[-1].rstrip(" ,.;:") + "…"
    card = (x0, top_y, x1, top_y + len(lines) * lh + 2 * pad)
    design.rounded_card(img, card, 40, (255, 255, 255, 248))
    design.text_block(img, lines, fnt, lh, w // 2, top_y + pad, fill=DARK, shadow=0)

    y = card[3] + 90
    label = DIFFICULTY.get(item.get("difficulty", ""), "") if kind in ("quiz", "truefalse") else ""
    if kind == "fill" and item.get("ref_label"):
        label = item["ref_label"].upper()
    if label:
        _pill(img, label, w // 2, y, 40, (255, 255, 255))
        y += 110
    _big(img, "VOCÊ SABE?" if kind != "verse" else "LEIA ATÉ O FIM", "sans_black", 900, 96, y + 40, accent)
    design.watermark(img, handle, min(h - 60, y + 190), 38)
    img.convert("RGB").save(out, quality=90)


def long_cover(total_n: int, minutes: int, seed: int, handle: str, out: Path) -> None:
    w, h = LONG_SIZE
    pal = design.palette_for("desafio", seed)
    img = design.background(w, h, pal, seed)
    img.alpha_composite(design.bokeh(w, h, pal, seed + 1, count=14))
    accent = pal.accent + (255,)
    d = ImageDraw.Draw(img)

    # esquerda: número gigante + "PERGUNTAS"
    left_cx = 330
    num = str(total_n)
    size = 330
    while design.font("sans_black", size).getlength(num) > 520:
        size -= 10
    fnt = design.font("sans_black", size)
    d.text((left_cx, 300 + size // 14), num, font=fnt, fill=(0, 0, 0, 170), anchor="mm",
           stroke_width=16, stroke_fill=(0, 0, 0, 170))
    d.text((left_cx, 300), num, font=fnt, fill=(255, 255, 255, 255), anchor="mm", stroke_width=12,
           stroke_fill=STROKE)
    d.text((left_cx, 505), "PERGUNTAS", font=design.font("sans_black", 76), fill=accent, anchor="mm",
           stroke_width=6, stroke_fill=STROKE)

    # direita: selo + promessa em 3 linhas
    right_cx = 940
    _pill(img, "QUIZ BÍBLICO", right_cx, 120, 40, pal.accent)
    for i, (line, color) in enumerate((("SÓ 1%", accent), ("ACERTA", (255, 255, 255, 255)),
                                       ("TODAS!", (255, 255, 255, 255)))):
        d.text((right_cx, 250 + i * 118), line, font=design.font("sans_black", 116), fill=color, anchor="mm",
               stroke_width=8, stroke_fill=STROKE)

    # faixa inferior (fica à esquerda: o canto direito é da duração do YouTube)
    strip = f"FÁCIL ATÉ DIFÍCIL · {minutes} MIN"
    _pill(img, strip, 420, 640, 34, (255, 255, 255))
    if handle:
        d.text((w - 40, 40), handle, font=design.font("sans_bold", 28), fill=(255, 255, 255, 200), anchor="ra")
    img.convert("RGB").save(out, quality=90)
