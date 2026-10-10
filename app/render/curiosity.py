"""Template "Você sabia?": imagens 9:16, 4:5 e 1:1 com uma curiosidade bíblica.
Opcional: vídeo 9:16 (Reels/Shorts) se "curiosity" estiver em video.video_types."""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image

from . import design, video

LAYOUTS = {
    (1080, 1920): dict(label_y=300, area=(110, 400, 970, 1400), label_size=40, title=(84, 52),
                       text=(54, 34), ref_size=40, wm_y=1560, wm_size=34),
    (1080, 1350): dict(label_y=140, area=(100, 220, 980, 1130), label_size=36, title=(76, 46),
                       text=(48, 30), ref_size=36, wm_y=1262, wm_size=32),
    (1080, 1080): dict(label_y=100, area=(100, 170, 980, 900), label_size=32, title=(66, 40),
                       text=(42, 26), ref_size=32, wm_y=1006, wm_size=30),
}


def _canvas(size) -> Image.Image:
    return Image.new("RGBA", size, (0, 0, 0, 0))


def _parts(size, item: dict, pal: design.Palette) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Título, texto e referência em camadas separadas (a imagem junta as três; o vídeo as revela)."""
    L = LAYOUTS[size]
    w = size[0]
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
    title_img, body_img, ref_img = _canvas(size), _canvas(size), _canvas(size)
    y = design.text_block(title_img, t_lines, t_font, t_lh, w // 2, y, fill=pal.accent + (255,))
    y = design.text_block(body_img, b_lines, b_font, b_lh, w // 2, y + gap)
    design.text_block(ref_img, [item["ref_label"].upper()], design.font("sans_bold", L["ref_size"]),
                      int(L["ref_size"] * 1.4), w // 2, y + int(L["ref_size"] * 0.7),
                      fill=pal.accent + (255,), tracking=3)
    return title_img, body_img, ref_img


def still(size, item: dict, pal: design.Palette, seed: int, handle: str) -> Image.Image:
    L = LAYOUTS[size]
    img = design.background(*size, pal, seed)
    img.alpha_composite(design.bokeh(*size, pal, seed + 1, count=14))
    design.label(img, "VOCÊ SABIA?", L["label_y"], L["label_size"], pal.accent)
    for part in _parts(size, item, pal):
        img.alpha_composite(part)
    design.watermark(img, handle, L["wm_y"], L["wm_size"])
    return img.convert("RGB")


def wants_video(settings: dict) -> bool:
    return "curiosity" in settings.get("video", {}).get("video_types", ["quiz"])


def timeline(item: dict, min_s: float, max_s: float) -> dict:
    read = min(18.0, max(5.0, 2.5 + len(item["text"]) / 13))
    cta = 3.0
    total = 0.5 + 1.4 + read + cta
    if total < min_s:
        read += min_s - total
    elif total > max_s:
        read = max(4.0, read - (total - max_s))
    main_out = 0.5 + 1.4 + read
    return {"title_in": 0.5, "body_in": 1.9, "ref_in": 2.9, "main_out": main_out,
            "total": round(main_out + cta, 2)}


def render_video(item: dict, pal: design.Palette, seed: int, handle: str, settings: dict,
                 out_dir: Path, work: Path) -> tuple[Path, float]:
    size = (1080, 1920)
    L = LAYOUTS[size]
    vcfg = settings.get("video", {})
    tl = timeline(item, vcfg.get("min_seconds", 15), vcfg.get("max_seconds", 30))
    total = tl["total"]
    bg = design.background(*size, pal, seed)
    layers: list[video.Layer] = [
        video.Layer(design.bokeh(*size, pal, seed + 1), 0, total * 0.6, fade_in=1.5, fade_out=2.5, slide=0),
        video.Layer(design.bokeh(*size, pal, seed + 2), total * 0.45, total, fade_in=2.5, slide=0),
    ]
    lab = _canvas(size)
    design.label(lab, "VOCÊ SABIA?", L["label_y"], L["label_size"], pal.accent)
    layers.append(video.layer(lab, 0.2, tl["main_out"], slide=0))
    title_img, body_img, ref_img = _parts(size, item, pal)
    layers.append(video.layer(title_img, tl["title_in"], tl["main_out"], fade_in=0.7))
    layers.append(video.layer(body_img, tl["body_in"], tl["main_out"], fade_in=0.8))
    layers.append(video.layer(ref_img, tl["ref_in"], tl["main_out"], fade_in=0.6))

    cta = _canvas(size)
    design.text_block(cta, ["Você já sabia?"], design.font("serif_bold", 104), 130, size[0] // 2, 700,
                      fill=pal.accent + (255,))
    fnt, lines, lh = design.fit("Comente SIM ou NÃO e compartilhe com quem ama a Palavra", "sans_bold",
                                800, 260, 54, 40)
    design.text_block(cta, lines, fnt, lh, size[0] // 2, 900)
    layers.append(video.layer(cta, tl["main_out"], total, fade_in=0.5))
    wm = _canvas(size)
    design.watermark(wm, handle, L["wm_y"], L["wm_size"])
    layers.append(video.layer(wm, 0.0, total, fade_in=0.01, slide=0))
    out = out_dir / "video_sem_musica.mp4"
    video.compose(bg, layers, total, out, work)
    return out, total


def render(item: dict, settings: dict, out_dir: Path, seed: int, track_path, rng: random.Random,
           work: Path) -> dict:
    handle = settings.get("brand", {}).get("handle", "")
    pal = design.palette_for("alegria", seed)
    images = {"imagem_story.jpg": (1080, 1920), "imagem_vertical.jpg": (1080, 1350),
              "imagem_quadrada.jpg": (1080, 1080)}
    for name, size in images.items():
        still(size, item, pal, seed, handle).save(out_dir / name, quality=92)
    if not wants_video(settings) or track_path is None:
        return {"poster": "imagem_story.jpg", "images": list(images), "duration": 0}
    silent, total = render_video(item, pal, seed, handle, settings, out_dir, work)
    with_music = out_dir / "video_com_musica.mp4"
    video.add_music(silent, track_path, total, settings.get("video", {}).get("music_volume", 0.16),
                    with_music, rng)
    video.poster(silent, min(4.0, total / 3), out_dir / "capa.jpg")
    return {"video_music": "video_com_musica.mp4", "video_silent": "video_sem_musica.mp4",
            "poster": "capa.jpg", "images": list(images), "duration": total}
