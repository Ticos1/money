"""Peças visuais: fundos, paletas, texto ajustável, cartões e marca d'água.

Tudo é desenhado com Pillow (sem fotos de terceiros = sem risco de direitos).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import FONTS_DIR

FONT = {
    "serif": FONTS_DIR / "PlayfairDisplay-SemiBold.ttf",
    "serif_bold": FONTS_DIR / "PlayfairDisplay-Bold.ttf",
    "serif_italic": FONTS_DIR / "PlayfairDisplay-MediumItalic.ttf",
    "sans": FONTS_DIR / "Montserrat-Medium.ttf",
    "sans_bold": FONTS_DIR / "Montserrat-Bold.ttf",
    "sans_black": FONTS_DIR / "Montserrat-ExtraBold.ttf",
}

WHITE = (255, 255, 255, 255)


@dataclass(frozen=True)
class Palette:
    top: tuple[int, int, int]
    bottom: tuple[int, int, int]
    glow: tuple[int, int, int]
    accent: tuple[int, int, int]


PALETTES = {
    "reflexao": [
        Palette((10, 14, 38), (44, 26, 78), (120, 100, 230), (232, 194, 122)),
        Palette((8, 24, 40), (22, 60, 84), (90, 170, 210), (240, 205, 140)),
        Palette((20, 12, 30), (70, 34, 60), (210, 120, 160), (245, 210, 150)),
    ],
    "alegria": [
        Palette((30, 14, 8), (128, 60, 20), (255, 196, 110), (255, 226, 160)),
        Palette((12, 30, 34), (20, 96, 92), (130, 230, 200), (255, 220, 140)),
        Palette((34, 12, 30), (140, 52, 70), (255, 160, 130), (255, 230, 170)),
    ],
    "desafio": [
        Palette((6, 22, 40), (10, 64, 92), (60, 200, 230), (255, 204, 70)),
        Palette((22, 8, 40), (64, 24, 110), (170, 110, 255), (255, 204, 70)),
    ],
}


def palette_for(mood: str, seed: int) -> Palette:
    options = PALETTES.get(mood, PALETTES["reflexao"])
    return options[seed % len(options)]


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT[kind]), size)


# ---------------------------------------------------------------- fundos

def background(w: int, h: int, pal: Palette, seed: int) -> Image.Image:
    """Degradê vertical + brilho radial + raios de luz + vinheta."""
    rng = random.Random(seed)
    grad = Image.new("RGB", (1, 256))
    for y in range(256):
        t = y / 255
        t = t * t * (3 - 2 * t)
        grad.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(pal.top, pal.bottom)))
    img = grad.resize((w, h), Image.BICUBIC).convert("RGBA")

    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy = w * rng.uniform(0.3, 0.7), h * rng.uniform(0.15, 0.35)
    r = max(w, h) * 0.45
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=pal.glow + (90,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(max(w, h) * 0.12)))

    rays = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rays)
    origin = (w * rng.uniform(0.2, 0.8), -h * 0.1)
    for _ in range(5):
        ang = math.radians(rng.uniform(60, 120))
        spread = math.radians(rng.uniform(2, 5))
        length = h * 1.4
        p1 = (origin[0] + length * math.cos(ang - spread), origin[1] + length * math.sin(ang - spread))
        p2 = (origin[0] + length * math.cos(ang + spread), origin[1] + length * math.sin(ang + spread))
        rd.polygon([origin, p1, p2], fill=(255, 255, 255, rng.randint(10, 22)))
    img.alpha_composite(rays.filter(ImageFilter.GaussianBlur(w * 0.03)))

    vignette = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse([-w * 0.3, -h * 0.2, w * 1.3, h * 1.2], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(w * 0.15))
    dark = Image.new("RGBA", (w, h), (0, 0, 0, 150))
    dark.putalpha(vignette.point(lambda v: int((255 - v) * 0.6)))
    img.alpha_composite(dark)
    return img


def bokeh(w: int, h: int, pal: Palette, seed: int, count: int = 22) -> Image.Image:
    """Camada transparente de luzes desfocadas (usada animada no vídeo)."""
    rng = random.Random(seed)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(count):
        r = rng.uniform(w * 0.01, w * 0.06)
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        color = pal.glow if rng.random() < 0.6 else pal.accent
        d.ellipse([x - r, y - r, x + r, y + r], fill=color + (rng.randint(25, 70),))
    return layer.filter(ImageFilter.GaussianBlur(w * 0.008))


# ---------------------------------------------------------------- texto

def wrap(text: str, fnt: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if fnt.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit(text: str, kind: str, max_w: int, max_h: int, start: int, minimum: int,
        spacing: float = 1.28) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Maior tamanho de fonte em que o texto cabe na caixa."""
    size = start
    while True:
        fnt = font(kind, size)
        lines = wrap(text, fnt, max_w)
        line_h = int(size * spacing)
        widest = max(fnt.getlength(line) for line in lines)
        if (len(lines) * line_h <= max_h and widest <= max_w) or size <= minimum:
            return fnt, lines, line_h
        size -= 2


def text_block(canvas: Image.Image, lines: list[str], fnt: ImageFont.FreeTypeFont, line_h: int,
               cx: int, top: int, fill=WHITE, shadow: int = 150, tracking: int = 0) -> int:
    """Desenha linhas centralizadas com sombra suave. Devolve o y final."""
    w, h = canvas.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    sd = ImageDraw.Draw(shadow_layer)
    y = top
    ascent = fnt.getmetrics()[0]
    for line in lines:
        if tracking:
            widths = [fnt.getlength(c) + tracking for c in line]
            x = cx - (sum(widths) - tracking) / 2
            for c, cw in zip(line, widths):
                sd.text((x, y + 4 + (line_h - ascent) / 2), c, font=fnt, fill=(0, 0, 0, shadow))
                d.text((x, y + (line_h - ascent) / 2), c, font=fnt, fill=fill)
                x += cw
        else:
            lw = fnt.getlength(line)
            pos = (cx - lw / 2, y + (line_h - ascent) / 2)
            sd.text((pos[0], pos[1] + 4), line, font=fnt, fill=(0, 0, 0, shadow))
            d.text(pos, line, font=fnt, fill=fill)
        y += line_h
    if shadow:
        canvas.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(7)))
    canvas.alpha_composite(layer)
    return y


def label(canvas: Image.Image, text: str, cy: int, size: int, color) -> None:
    """Rótulo em caixa alta, espaçado, com fios decorativos dos lados."""
    fnt = font("sans_bold", size)
    tracking = int(size * 0.18)
    width = sum(fnt.getlength(c) + tracking for c in text) - tracking
    cx = canvas.width // 2
    text_block(canvas, [text], fnt, int(size * 1.3), cx, cy - int(size * 0.65), fill=color + (255,),
               shadow=90, tracking=tracking)
    d = ImageDraw.Draw(canvas)
    gap, line_w = size * 0.8, size * 2.2
    for sign in (-1, 1):
        x0 = cx + sign * (width / 2 + gap)
        x1 = x0 + sign * line_w
        d.line([(min(x0, x1), cy), (max(x0, x1), cy)], fill=color + (200,), width=max(2, size // 14))


def watermark(canvas: Image.Image, handle: str, cy: int, size: int) -> None:
    if not handle:
        return
    fnt = font("sans_bold", size)
    text_block(canvas, [handle], fnt, int(size * 1.3), canvas.width // 2, cy - int(size * 0.65),
               fill=(255, 255, 255, 190), shadow=120)


def rounded_card(canvas: Image.Image, box: tuple[int, int, int, int], radius: int, fill,
                 outline=None, width: int = 0, shadow: bool = True) -> None:
    if shadow:
        sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([box[0], box[1] + 8, box[2], box[3] + 8], radius,
                                             fill=(0, 0, 0, 90))
        canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(layer)


def check_mark(canvas: Image.Image, cx: int, cy: int, size: int, color=WHITE) -> None:
    d = ImageDraw.Draw(canvas)
    pts = [(cx - size * 0.45, cy), (cx - size * 0.1, cy + size * 0.35), (cx + size * 0.5, cy - size * 0.4)]
    d.line(pts, fill=color, width=max(4, size // 6), joint="curve")


def crop_layer(img: Image.Image, pad: int = 12) -> tuple[Image.Image, int, int]:
    """Recorta a área visível de uma camada (deixa o vídeo mais leve de montar)."""
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        return Image.new("RGBA", (2, 2), (0, 0, 0, 0)), 0, 0
    x0, y0 = max(0, bbox[0] - pad), max(0, bbox[1] - pad)
    x1, y1 = min(img.width, bbox[2] + pad), min(img.height, bbox[3] + pad)
    # dimensões pares evitam problemas no encoder
    if (x1 - x0) % 2:
        x1 = min(img.width, x1 + 1) if x1 < img.width else x1 - 1
    if (y1 - y0) % 2:
        y1 = min(img.height, y1 + 1) if y1 < img.height else y1 - 1
    return img.crop((x0, y0, x1, y1)), x0, y0
