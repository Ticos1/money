"""Template "Você sabia?": imagens 9:16, 4:5 e 1:1 com uma curiosidade bíblica."""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image

from . import design

LAYOUTS = {
    (1080, 1920): dict(label_y=300, area=(110, 400, 970, 1400), label_size=40, title=(84, 52),
                       text=(54, 34), ref_size=40, wm_y=1560, wm_size=34),
    (1080, 1350): dict(label_y=140, area=(100, 220, 980, 1130), label_size=36, title=(76, 46),
                       text=(48, 30), ref_size=36, wm_y=1262, wm_size=32),
    (1080, 1080): dict(label_y=100, area=(100, 170, 980, 900), label_size=32, title=(66, 40),
                       text=(42, 26), ref_size=32, wm_y=1006, wm_size=30),
}


def still(size, item: dict, pal: design.Palette, seed: int, handle: str) -> Image.Image:
    L = LAYOUTS[size]
    w = size[0]
    img = design.background(*size, pal, seed)
    img.alpha_composite(design.bokeh(*size, pal, seed + 1, count=14))
    design.label(img, "VOCÊ SABIA?", L["label_y"], L["label_size"], pal.accent)
    x0, y0, x1, y1 = L["area"]
    box_w, box_h = x1 - x0, y1 - y0
    ref_h = int(L["ref_size"] * 2.2)
    t_font, t_lines, t_lh = design.fit(item["title"], "sans_black", box_w, int(box_h * 0.32),
                                       L["title"][0], L["title"][1], spacing=1.15)
    gap = int(L["text"][0] * 0.9)
    remaining = box_h - len(t_lines) * t_lh - gap - ref_h
    b_font, b_lines, b_lh = design.fit(item["text"], "serif", box_w, remaining, L["text"][0], L["text"][1],
                                       spacing=1.35)
    total = len(t_lines) * t_lh + gap + len(b_lines) * b_lh + ref_h
    y = y0 + (box_h - total) // 2
    y = design.text_block(img, t_lines, t_font, t_lh, w // 2, y, fill=pal.accent + (255,))
    y = design.text_block(img, b_lines, b_font, b_lh, w // 2, y + gap)
    design.text_block(img, [item["ref_label"].upper()], design.font("sans_bold", L["ref_size"]),
                      int(L["ref_size"] * 1.4), w // 2, y + int(L["ref_size"] * 0.7),
                      fill=pal.accent + (255,), tracking=3)
    design.watermark(img, handle, L["wm_y"], L["wm_size"])
    return img.convert("RGB")


def render(item: dict, settings: dict, out_dir: Path, seed: int, track_path, rng: random.Random,
           work: Path) -> dict:
    handle = settings.get("brand", {}).get("handle", "")
    pal = design.palette_for("alegria", seed)
    images = {"imagem_story.jpg": (1080, 1920), "imagem_vertical.jpg": (1080, 1350),
              "imagem_quadrada.jpg": (1080, 1080)}
    for name, size in images.items():
        still(size, item, pal, seed, handle).save(out_dir / name, quality=92)
    return {"poster": "imagem_story.jpg", "images": list(images), "duration": 0}
