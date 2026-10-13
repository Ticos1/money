"""Template "Verdadeiro ou falso?": pergunta do banco + uma resposta mostrada; contagem
regressiva; revela se é verdade e qual é a resposta certa. Vídeo 9:16 com música."""
from __future__ import annotations

import random
from pathlib import Path

from PIL import ImageDraw

from . import design, quiz, video

GREEN = (38, 166, 91)
RED = (205, 55, 55)
DARK = (28, 28, 40, 255)


def _button(size, box, text, color, state="normal"):
    """state: normal | right | wrong"""
    img = quiz._canvas(size)
    x0, y0, x1, y1 = box
    h = y1 - y0
    if state == "wrong":
        design.rounded_card(img, box, h // 2, (60, 60, 70, 170), shadow=False)
    else:
        outline = (255, 255, 255, 255) if state == "right" else None
        design.rounded_card(img, box, h // 2, color + (250,), outline=outline, width=6 if outline else 0)
    d = ImageDraw.Draw(img)
    fill = (255, 255, 255, 120) if state == "wrong" else (255, 255, 255, 255)
    d.text(((x0 + x1) // 2, (y0 + y1) // 2), text, font=design.font("sans_black", 50), fill=fill, anchor="mm")
    return img


def timeline() -> dict:
    return {"q_in": 2.4, "claim_in": 3.4, "buttons_in": 4.0, "count_in": 5.2, "count": 5,
            "reveal": 10.2, "end_in": 14.5, "total": 17.0}


def render_video(item, pal, seed, handle, settings, out_dir: Path, work: Path) -> tuple[Path, float]:
    size = (1080, 1920)
    w, h = size
    L = quiz.LAYOUTS[size]
    tl = timeline()
    total = tl["total"]
    bg = design.background(w, h, pal, seed)
    layers = [
        video.Layer(design.bokeh(w, h, pal, seed + 1), 0, total * 0.6, fade_in=1.2, fade_out=2.5, slide=0),
        video.Layer(design.bokeh(w, h, pal, seed + 2), total * 0.45, total, fade_in=2.5, slide=0),
    ]
    hook = quiz._canvas(size)
    design.text_block(hook, ["VERDADEIRO"], design.font("sans_black", 140), 160, w // 2, 600, fill=GREEN + (255,))
    design.text_block(hook, ["OU FALSO?"], design.font("sans_black", 140), 160, w // 2, 770, fill=RED + (255,))
    design.text_block(hook, ["Só 1% acerta de primeira"], design.font("sans_bold", 54), 70, w // 2, 980)
    layers.append(video.layer(hook, 0.15, tl["q_in"], fade_in=0.3, fade_out=0.3, slide=60))

    lab = quiz._canvas(size)
    design.label(lab, "VERDADEIRO OU FALSO?", L["label_y"], L["label_size"], pal.accent)
    layers.append(video.layer(lab, tl["q_in"] - 0.1, tl["end_in"], slide=0))

    geo = quiz._geometry(size, item)
    layers.append(video.layer(quiz._question_layer(size, item, geo), tl["q_in"], tl["end_in"], slide=50))

    # a "resposta" que o vídeo afirma (pode ser verdade ou não)
    claim = quiz._canvas(size)
    top = geo["card"][3] + 50
    fnt, lines, lh = design.fit(f"Resposta: {item['shown']}", "sans_black", 820, 220, 64, 40, spacing=1.15)
    box = (110, top, 970, top + len(lines) * lh + 70)
    design.rounded_card(claim, box, 40, pal.accent + (250,))
    design.text_block(claim, lines, fnt, lh, w // 2, top + 35, fill=DARK, shadow=0)
    layers.append(video.layer(claim, tl["claim_in"], tl["end_in"], fade_in=0.4, slide=30))

    by = box[3] + 60
    left, right = (110, by, 520, by + 140), (560, by, 970, by + 140)
    layers.append(video.layer(_button(size, left, "VERDADEIRO", GREEN), tl["buttons_in"], tl["reveal"], slide=20))
    layers.append(video.layer(_button(size, right, "FALSO", RED), tl["buttons_in"] + 0.2, tl["reveal"], slide=20))

    cy = min(by + 140 + 150, L["wm_y"] - 130)
    for k in range(tl["count"]):
        c = quiz._canvas(size)
        d = ImageDraw.Draw(c)
        r = 78
        d.ellipse([w // 2 - r, cy - r, w // 2 + r, cy + r], outline=pal.accent + (255,), width=8, fill=(0, 0, 0, 90))
        d.text((w // 2, cy + 4), str(tl["count"] - k), font=design.font("sans_black", 92),
               fill=(255, 255, 255, 255), anchor="mm")
        start = tl["count_in"] + k
        layers.append(video.layer(c, start, start + 1.0, fade_in=0.12, fade_out=0.12, slide=0))

    true_state, false_state = ("right", "wrong") if item["is_true"] else ("wrong", "right")
    layers.append(video.layer(_button(size, left, "VERDADEIRO", GREEN, true_state), tl["reveal"], tl["end_in"],
                              fade_in=0.2, slide=0))
    layers.append(video.layer(_button(size, right, "FALSO", RED, false_state), tl["reveal"], tl["end_in"],
                              fade_in=0.2, slide=0))
    ans = quiz._canvas(size)
    verdict = "É VERDADE!" if item["is_true"] else "É FALSO!"
    y = design.text_block(ans, [verdict], design.font("sans_black", 64), 76, w // 2, cy - 90,
                          fill=(GREEN if item["is_true"] else RED) + (255,))
    fnt, lines, lh = design.fit(f"Certo: {item['correct']} ({item['ref_label']})", "sans_bold", 880, 200, 44, 32)
    design.text_block(ans, lines, fnt, lh, w // 2, y + 6)
    layers.append(video.layer(ans, tl["reveal"] + 0.2, tl["end_in"], fade_in=0.3))

    end = quiz._canvas(size)
    ImageDraw.Draw(end).rectangle([0, 0, w, h], fill=(0, 0, 0, 165))
    design.text_block(end, ["Você acertou?"], design.font("serif_bold", 104), 130, w // 2, 640, fill=pal.accent + (255,))
    fnt, lines, lh = design.fit("Comente V ou F e desafie um amigo!", "sans_bold", 820, 220, 56, 40)
    yy = design.text_block(end, lines, fnt, lh, w // 2, 810)
    if handle:
        design.text_block(end, [f"Siga {handle} para mais"], design.font("sans_bold", 46), 60, w // 2, yy + 40)
    layers.append(video.Layer(end, tl["end_in"], total, fade_in=0.4, slide=0))

    wm = quiz._canvas(size)
    design.watermark(wm, handle, L["wm_y"], L["wm_size"])
    layers.append(video.layer(wm, 0.0, tl["end_in"], fade_in=0.01, slide=0))
    out = out_dir / "video_sem_musica.mp4"
    video.compose(bg, layers, total, out, work)
    return out, total


def render(item: dict, settings: dict, out_dir: Path, seed: int, track_path: Path, rng: random.Random,
           work: Path) -> dict:
    handle = settings.get("brand", {}).get("handle", "")
    pal = design.palette_for("desafio", seed)
    silent, total = render_video(item, pal, seed, handle, settings, out_dir, work)
    with_music = out_dir / "video_com_musica.mp4"
    video.add_music(silent, track_path, total, settings.get("video", {}).get("music_volume", 0.16),
                    with_music, rng)
    video.poster(silent, timeline()["count_in"], out_dir / "capa.jpg")
    return {"video_music": "video_com_musica.mp4", "video_silent": "video_sem_musica.mp4",
            "poster": "capa.jpg", "images": [], "duration": total}
