"""Template "Versículo do dia": vídeo 9:16 em 3 cenas + imagens 1:1 e 4:5.

Cena 1: versículo + referência   Cena 2: frase de reflexão   Cena 3: chamada final
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image

from . import design, video

# posições pensadas para não ficar embaixo dos botões do TikTok/Reels
LAYOUTS = {
    (1080, 1920): dict(label_y=300, area=(110, 430, 970, 1330), label_size=34, verse=(84, 44),
                       ref_size=44, wm_y=1560, wm_size=34),
    (1080, 1350): dict(label_y=150, area=(100, 240, 980, 1120), label_size=30, verse=(78, 38),
                       ref_size=40, wm_y=1262, wm_size=32),
    (1080, 1080): dict(label_y=110, area=(100, 190, 980, 900), label_size=28, verse=(70, 34),
                       ref_size=38, wm_y=1006, wm_size=30),
}


def _canvas(size) -> Image.Image:
    return Image.new("RGBA", size, (0, 0, 0, 0))


def _verse_and_ref(size, item: dict, pal: design.Palette) -> tuple[Image.Image, Image.Image]:
    L = LAYOUTS[size]
    x0, y0, x1, y1 = L["area"]
    ref_h = int(L["ref_size"] * 2.2)
    fnt, lines, lh = design.fit(f"“{item['verse_text']}”", "serif", x1 - x0, (y1 - y0) - ref_h,
                                L["verse"][0], L["verse"][1], spacing=1.3)
    total = len(lines) * lh + ref_h
    top = y0 + ((y1 - y0) - total) // 2
    verse_img = _canvas(size)
    end = design.text_block(verse_img, lines, fnt, lh, size[0] // 2, top)
    ref_img = _canvas(size)
    design.text_block(ref_img, [item["ref_label"].upper()], design.font("sans_bold", L["ref_size"]),
                      int(L["ref_size"] * 1.4), size[0] // 2, end + int(L["ref_size"] * 0.7),
                      fill=pal.accent + (255,), tracking=3)
    return verse_img, ref_img


def still(size, item: dict, pal: design.Palette, seed: int, handle: str) -> Image.Image:
    L = LAYOUTS[size]
    img = design.background(*size, pal, seed)
    img.alpha_composite(design.bokeh(*size, pal, seed + 1, count=14))
    design.label(img, "VERSÍCULO DO DIA", L["label_y"], L["label_size"], pal.accent)
    verse_img, ref_img = _verse_and_ref(size, item, pal)
    img.alpha_composite(verse_img)
    img.alpha_composite(ref_img)
    design.watermark(img, handle, L["wm_y"], L["wm_size"])
    return img.convert("RGB")


def timeline(item: dict, min_s: float, max_s: float) -> dict:
    verse_dur = min(16.0, max(6.0, 2.5 + len(item["verse_text"]) / 14))
    refl_dur = min(7.0, max(4.0, 2.0 + len(item["on_screen"]) / 13))
    cta_dur = 3.0
    total = 0.7 + verse_dur + 0.2 + refl_dur + cta_dur
    if total < min_s:
        verse_dur += min_s - total
    elif total > max_s:
        verse_dur -= total - max_s
    t1 = 0.7 + verse_dur
    t2 = t1 + 0.2 + refl_dur
    return {"verse_in": 0.7, "verse_out": t1, "refl_in": t1 + 0.2, "refl_out": t2,
            "cta_in": t2, "total": round(t2 + cta_dur, 2)}


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
    design.label(lab, "VERSÍCULO DO DIA", L["label_y"], L["label_size"], pal.accent)
    layers.append(video.layer(lab, 0.25, tl["refl_out"], slide=0))

    verse_img, ref_img = _verse_and_ref(size, item, pal)
    layers.append(video.layer(verse_img, tl["verse_in"], tl["verse_out"], fade_in=0.8))
    layers.append(video.layer(ref_img, tl["verse_in"] + 1.0, tl["verse_out"]))

    refl = _canvas(size)
    design.label(refl, "PARA REFLETIR", 620, 32, pal.accent)
    fnt, lines, lh = design.fit(item["on_screen"], "serif_italic", 840, 520, 82, 46)
    design.text_block(refl, lines, fnt, lh, size[0] // 2, 700 + (520 - len(lines) * lh) // 2)
    layers.append(video.layer(refl, tl["refl_in"], tl["refl_out"], fade_in=0.6))

    cta = _canvas(size)
    design.text_block(cta, ["Amém?"], design.font("serif_bold", 120), 150, size[0] // 2, 700,
                      fill=pal.accent + (255,))
    fnt, lines, lh = design.fit("Compartilhe com alguém que precisa ouvir isso hoje", "sans_bold",
                                800, 260, 54, 40)
    design.text_block(cta, lines, fnt, lh, size[0] // 2, 900)
    layers.append(video.layer(cta, tl["cta_in"], total, fade_in=0.5))

    wm = _canvas(size)
    design.watermark(wm, handle, L["wm_y"], L["wm_size"])
    layers.append(video.layer(wm, 0.0, total, fade_in=0.01, slide=0))

    out = out_dir / "video_sem_musica.mp4"
    video.compose(bg, layers, total, out, work)
    return out, total


def wants_video(settings: dict) -> bool:
    """Versículo sai como imagem, a não ser que "verse" esteja em video.video_types."""
    return "verse" in settings.get("video", {}).get("video_types", ["quiz"])


def render(item: dict, settings: dict, out_dir: Path, seed: int, track_path: Path | None,
           rng: random.Random, work: Path) -> dict:
    handle = settings.get("brand", {}).get("handle", "")
    pal = design.palette_for(item.get("mood", "reflexao"), seed)
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
    return {
        "video_music": "video_com_musica.mp4",
        "video_silent": "video_sem_musica.mp4",
        "poster": "capa.jpg",
        "images": list(images),
        "duration": total,
    }
