"""Template "Desafio de quiz": gancho "SÓ 1% ACERTA", pergunta e alternativas já no primeiro quadro
→ "Comente a letra" → contagem regressiva (3s) → resposta revelada → volta à pergunta sem marcação,
para o vídeo (8 a 12 s) repetir sem emenda.
Imagens: pergunta (1:1 e 4:5) + resposta (1:1 e 4:5) para carrossel."""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw

from . import design, video

LETTERS = "ABCD"
DARK_TEXT = (28, 28, 40, 255)
GREEN = (38, 166, 91)

LAYOUTS = {
    (1080, 1920): dict(label_y=250, label_size=34, card_top=320, card_x=(100, 980), q_size=(62, 40),
                       q_max_h=380, opt_h=118, opt_gap=24, opt_size=(46, 30), gap=44, wm_y=1590,
                       wm_size=34),
    (1080, 1350): dict(label_y=110, label_size=30, card_top=170, card_x=(90, 990), q_size=(56, 36),
                       q_max_h=300, opt_h=104, opt_gap=20, opt_size=(42, 28), gap=36, wm_y=1270,
                       wm_size=30),
    # 16:9 (vídeo longo do YouTube): pergunta no topo e alternativas em grade 2x2
    (1280, 720): dict(label_y=40, label_size=26, card_top=76, card_x=(70, 1210), q_size=(44, 30),
                      q_max_h=170, opt_h=96, opt_gap=18, opt_size=(30, 22), gap=26, wm_y=684,
                      wm_size=24),
    (1080, 1080): dict(label_y=80, label_size=26, card_top=125, card_x=(90, 990), q_size=(48, 32),
                       q_max_h=220, opt_h=86, opt_gap=16, opt_size=(36, 26), gap=26, wm_y=1030,
                       wm_size=28),
}


def _canvas(size) -> Image.Image:
    return Image.new("RGBA", size, (0, 0, 0, 0))


def _geometry(size, item: dict) -> dict:
    """Calcula onde ficam o cartão da pergunta e as 4 alternativas."""
    L = LAYOUTS[size]
    x0, x1 = L["card_x"]
    pad = int(L["q_size"][0] * 0.65)
    fnt, lines, lh = design.fit(item["question"], "sans_bold", x1 - x0 - 2 * pad, L["q_max_h"],
                                L["q_size"][0], L["q_size"][1], spacing=1.22)
    card = (x0, L["card_top"], x1, L["card_top"] + len(lines) * lh + 2 * pad)
    opts = []
    y = card[3] + L["gap"]
    if size[0] > size[1]:  # horizontal: 2 colunas x 2 linhas
        col_w = (x1 - x0 - L["opt_gap"]) // 2
        for i in range(4):
            cx0 = x0 + (i % 2) * (col_w + L["opt_gap"])
            cy0 = y + (i // 2) * (L["opt_h"] + L["opt_gap"])
            opts.append((cx0, cy0, cx0 + col_w, cy0 + L["opt_h"]))
        return {"card": card, "q": (fnt, lines, lh, pad), "opts": opts,
                "end": y + 2 * L["opt_h"] + L["opt_gap"]}
    for _ in range(4):
        opts.append((x0, y, x1, y + L["opt_h"]))
        y += L["opt_h"] + L["opt_gap"]
    return {"card": card, "q": (fnt, lines, lh, pad), "opts": opts, "end": y - L["opt_gap"]}


def _question_layer(size, item: dict, geo: dict) -> Image.Image:
    img = _canvas(size)
    card = geo["card"]
    fnt, lines, lh, pad = geo["q"]
    design.rounded_card(img, card, 34, (255, 255, 255, 244))
    design.text_block(img, lines, fnt, lh, (card[0] + card[2]) // 2, card[1] + pad, fill=DARK_TEXT,
                      shadow=0)
    return img


def _option_layer(size, item: dict, geo: dict, i: int, pal: design.Palette,
                  state: str = "normal") -> Image.Image:
    """state: normal | correct | dim"""
    L = LAYOUTS[size]
    img = _canvas(size)
    x0, y0, x1, y1 = geo["opts"][i]
    h = y1 - y0
    if state == "correct":
        design.rounded_card(img, (x0, y0, x1, y1), h // 2, GREEN + (250,), outline=(255, 255, 255, 255),
                            width=4)
    else:
        design.rounded_card(img, (x0, y0, x1, y1), h // 2, (255, 255, 255, 40),
                            outline=(255, 255, 255, 110), width=3, shadow=False)
    d = ImageDraw.Draw(img)
    r = int(h * 0.34)
    cx, cy = x0 + int(h * 0.5), (y0 + y1) // 2
    circle_fill = (255, 255, 255, 255) if state == "correct" else pal.accent + (255,)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=circle_fill)
    lf = design.font("sans_black", int(r * 1.15))
    if state == "correct":
        design.check_mark(img, cx, cy, int(r * 1.1), color=GREEN + (255,))
    else:
        d.text((cx, cy), LETTERS[i], font=lf, fill=DARK_TEXT, anchor="mm")
    tx0 = cx + r + int(h * 0.25)
    fnt, lines, lh = design.fit(item["options"][i], "sans_bold", x1 - tx0 - int(h * 0.35), h - 16,
                                L["opt_size"][0], L["opt_size"][1], spacing=1.12)
    ty = cy - len(lines) * lh // 2
    for line in lines:
        d.text((tx0, ty + lh // 2), line, font=fnt, fill=(255, 255, 255, 255), anchor="lm")
        ty += lh
    if state == "dim":
        shade = _canvas(size)
        ImageDraw.Draw(shade).rounded_rectangle((x0, y0, x1, y1), h // 2, fill=(0, 0, 0, 150))
        img.alpha_composite(shade)
    return img


def still_question(size, item, pal, seed, handle) -> Image.Image:
    L = LAYOUTS[size]
    img = design.background(*size, pal, seed)
    img.alpha_composite(design.bokeh(*size, pal, seed + 1, count=12))
    design.label(img, "DESAFIO BÍBLICO", L["label_y"], L["label_size"], pal.accent)
    geo = _geometry(size, item)
    img.alpha_composite(_question_layer(size, item, geo))
    for i in range(4):
        img.alpha_composite(_option_layer(size, item, geo, i, pal))
    hint_y = geo["end"] + int(L["gap"] * 1.6)
    if hint_y < L["wm_y"] - L["wm_size"] * 2:
        fnt = design.font("sans_bold", int(L["label_size"] * 1.05))
        design.text_block(img, ["Arraste para o lado e veja a resposta"], fnt, int(L["label_size"] * 1.5),
                          size[0] // 2, hint_y, fill=pal.accent + (255,))
    design.watermark(img, handle, L["wm_y"], L["wm_size"])
    return img.convert("RGB")


def still_answer(size, item, pal, seed, handle) -> Image.Image:
    L = LAYOUTS[size]
    w, h = size
    img = design.background(*size, pal, seed + 5)
    img.alpha_composite(design.bokeh(*size, pal, seed + 6, count=12))
    design.label(img, "RESPOSTA", L["label_y"], L["label_size"], pal.accent)
    x0, x1 = L["card_x"]
    top = L["card_top"]
    fnt, lines, lh = design.fit(item["question"], "sans_bold", x1 - x0, int(h * 0.16),
                                int(L["q_size"][0] * 0.8), 26)
    y = design.text_block(img, lines, fnt, lh, w // 2, top)
    pill_h = int(L["opt_h"] * 1.15)
    geo = {"opts": [(x0, y + 30, x1, y + 30 + pill_h)] * 4}
    img.alpha_composite(_option_layer(size, item, geo, item["answer"], pal, state="correct"))
    y = y + 30 + pill_h + int(L["gap"] * 1.2)
    rf = design.font("sans_bold", int(L["label_size"] * 1.25))
    y = design.text_block(img, [item["ref_label"].upper()], rf, int(L["label_size"] * 1.7), w // 2, y,
                          fill=pal.accent + (255,), tracking=3)
    max_h = L["wm_y"] - L["wm_size"] * 2 - y - 10
    if max_h > 80:
        fnt, lines, lh = design.fit(f"“{item['passage']}”", "serif_italic", x1 - x0 - 40, max_h,
                                    int(L["q_size"][0] * 0.78), 24, spacing=1.3)
        design.text_block(img, lines, fnt, lh, w // 2, y + 6)
    design.watermark(img, handle, L["wm_y"], L["wm_size"])
    return img.convert("RGB")


LOOP_MUSIC_FADES = {"fade_in": 0.3, "fade_out": 0.4}
LOOP_TAIL = 0.6  # depois da resposta, a pergunta volta sem marcação e fecha igual ao primeiro quadro
COMMENT_CTA = "Comente a letra: A, B, C ou D"


def timeline(item: dict, max_s: float) -> dict:
    """Pergunta e alternativas já no primeiro quadro; o vídeo fica entre 8 e 12 s."""
    read = min(5.0, max(2.5, (len(item["question"]) + sum(len(o) for o in item["options"])) / 22))
    count = 3
    count_in = read
    reveal = count_in + count
    end_in = reveal + 2.0
    total = min(end_in + LOOP_TAIL, max(8.0, max_s))
    return {"q_in": 0.0, "opts_in": [0.0] * 4, "count_in": count_in, "count": count, "reveal": reveal,
            "end_in": end_in, "total": round(total, 2)}


def loop_layers(size, pal, seed, total: float) -> list[video.Layer]:
    """Fundo montado para o vídeo emendar no começo ao repetir: o primeiro e o último quadro
    têm o mesmo fundo (bokeh 1), sem fade na entrada."""
    w, h = size
    b1 = design.bokeh(w, h, pal, seed + 1)
    return [
        video.Layer(b1, 0, total * 0.6, fade_in=0, fade_out=2.0, slide=0),
        video.Layer(design.bokeh(w, h, pal, seed + 2), total * 0.4, total - 0.1, fade_in=2.0,
                    fade_out=1.0, slide=0),
        video.Layer(b1, total - 1.1, total, fade_in=1.0, slide=0),
    ]


def hook_layer(size, text: str, pal: design.Palette) -> Image.Image:
    """Gancho curto em cima do cartão da pergunta (ex.: "SÓ 1% ACERTA")."""
    img = _canvas(size)
    L = LAYOUTS[size]
    fnt, lines, lh = design.fit(text, "sans_black", size[0] - 160, L["card_top"] - 130, 84, 52)
    design.text_block(img, lines, fnt, lh, size[0] // 2, 120, fill=pal.accent + (255,))
    return img


def cta_layer(size, text: str, cy: int, pal: design.Palette) -> Image.Image:
    """Pedido de comentário no lugar da contagem (some quando a contagem começa e volta no fim)."""
    img = _canvas(size)
    fnt, lines, lh = design.fit(text, "sans_black", size[0] - 200, 150, 54, 36)
    design.text_block(img, lines, fnt, lh, size[0] // 2, cy - len(lines) * lh // 2, fill=(255, 255, 255, 255))
    return img


def countdown_layers(size, tl: dict, cy: int, pal: design.Palette) -> list[video.Layer]:
    w = size[0]
    out = []
    for k in range(tl["count"]):
        c = _canvas(size)
        d = ImageDraw.Draw(c)
        r = 78
        d.ellipse([w // 2 - r, cy - r, w // 2 + r, cy + r], outline=pal.accent + (255,), width=8,
                  fill=(0, 0, 0, 90))
        d.text((w // 2, cy + 4), str(tl["count"] - k), font=design.font("sans_black", 92),
               fill=(255, 255, 255, 255), anchor="mm")
        start = tl["count_in"] + k
        out.append(video.layer(c, start, start + 1.0, fade_in=0.12, fade_out=0.12, slide=0))
    return out


def render_video(item, pal, seed, handle, settings, out_dir: Path, work: Path, hook: str = "SÓ 1% ACERTA ESSA",
                 cta: str = COMMENT_CTA) -> tuple[Path, float, float]:
    size = (1080, 1920)
    w, h = size
    L = LAYOUTS[size]
    tl = timeline(item, settings.get("video", {}).get("loop_max_seconds", 12))
    total = tl["total"]
    bg = design.background(*size, pal, seed)
    layers = loop_layers(size, pal, seed, total)
    first = dict(fade_in=0, slide=0)  # entra inteira já no primeiro quadro e fica até o fim
    layers.append(video.layer(hook_layer(size, hook, pal), 0, total, **first))

    geo = _geometry(size, item)
    layers.append(video.layer(_question_layer(size, item, geo), 0, total, **first))
    for i in range(4):
        layers.append(video.layer(_option_layer(size, item, geo, i, pal), 0, total, **first))

    cy = min(geo["end"] + 150, L["wm_y"] - 130)
    cta_img = cta_layer(size, cta, cy, pal)
    layers.append(video.layer(cta_img, 0, tl["count_in"], fade_in=0, fade_out=0.2, slide=0))
    layers += countdown_layers(size, tl, cy, pal)

    for i in range(4):
        state = "correct" if i == item["answer"] else "dim"
        layers.append(video.layer(_option_layer(size, item, geo, i, pal, state), tl["reveal"], tl["end_in"],
                                  fade_in=0.25, fade_out=0.3, slide=0))
    ans = _canvas(size)
    y = design.text_block(ans, [f"RESPOSTA: {LETTERS[item['answer']]}"], design.font("sans_black", 58), 70,
                          w // 2, cy - 70, fill=pal.accent + (255,))
    design.text_block(ans, [item["ref_label"]], design.font("sans_bold", 40), 52, w // 2, y)
    layers.append(video.layer(ans, tl["reveal"] + 0.2, tl["end_in"], fade_in=0.35, fade_out=0.3))
    layers.append(video.layer(cta_img, tl["end_in"] - 0.1, total, fade_in=0.3, slide=0))

    wm = _canvas(size)
    design.watermark(wm, handle, L["wm_y"], L["wm_size"])
    layers.append(video.layer(wm, 0.0, total, fade_in=0, slide=0))

    out = out_dir / "video_sem_musica.mp4"
    video.compose(bg, layers, total, out, work)
    return out, total, max(0.0, tl["count_in"] - 0.5)


def render(item: dict, settings: dict, out_dir: Path, seed: int, track_path: Path,
           rng: random.Random, work: Path) -> dict:
    handle = settings.get("brand", {}).get("handle", "")
    pal = design.palette_for("desafio", seed)
    silent, total, poster_at = render_video(item, pal, seed, handle, settings, out_dir, work)
    with_music = out_dir / "video_com_musica.mp4"
    video.add_music(silent, track_path, total, settings.get("video", {}).get("music_volume", 0.16),
                    with_music, rng, **LOOP_MUSIC_FADES)
    video.poster(silent, poster_at, out_dir / "capa.jpg")
    files = []
    for name, size, fn in (("pergunta_quadrada.jpg", (1080, 1080), still_question),
                           ("pergunta_vertical.jpg", (1080, 1350), still_question),
                           ("resposta_quadrada.jpg", (1080, 1080), still_answer),
                           ("resposta_vertical.jpg", (1080, 1350), still_answer)):
        fn(size, item, pal, seed, handle).save(out_dir / name, quality=92)
        files.append(name)
    return {
        "video_music": "video_com_musica.mp4",
        "video_silent": "video_sem_musica.mp4",
        "poster": "capa.jpg",
        "images": files,
        "duration": total,
    }
