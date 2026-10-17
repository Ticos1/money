"""Template "Verdadeiro ou falso?": pergunta do banco + uma resposta mostrada, já no primeiro quadro;
"Comente: V ou F"; contagem regressiva de 3s; revela se é verdade e qual é a resposta certa e volta à
pergunta sem marcação (loop de 8 a 12 s). Vídeo 9:16 com música."""
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


COMMENT_CTA = "Comente: V ou F"


def timeline(item: dict | None = None) -> dict:
    """Pergunta, resposta mostrada e botões já no primeiro quadro; o vídeo fica entre 8 e 12 s."""
    chars = len(item["question"]) + len(item["shown"]) if item else 120
    read = min(4.5, max(2.5, chars / 22))
    count_in = read
    reveal = count_in + 3
    end_in = reveal + 2.5
    return {"count_in": count_in, "count": 3, "reveal": reveal, "end_in": end_in,
            "total": round(end_in + quiz.LOOP_TAIL, 2)}


def render_video(item, pal, seed, handle, settings, out_dir: Path, work: Path) -> tuple[Path, float]:
    size = (1080, 1920)
    w, h = size
    L = quiz.LAYOUTS[size]
    tl = timeline(item)
    total = tl["total"]
    bg = design.background(w, h, pal, seed)
    layers = quiz.loop_layers(size, pal, seed, total)
    first = dict(fade_in=0, slide=0)  # entra inteira já no primeiro quadro e fica até o fim
    layers.append(video.layer(quiz.hook_layer(size, "VERDADEIRO OU FALSO?", pal), 0, total, **first))

    geo = quiz._geometry(size, item)
    layers.append(video.layer(quiz._question_layer(size, item, geo), 0, total, **first))

    # a "resposta" que o vídeo afirma (pode ser verdade ou não)
    claim = quiz._canvas(size)
    top = geo["card"][3] + 50
    fnt, lines, lh = design.fit(f"Resposta: {item['shown']}", "sans_black", 820, 220, 64, 40, spacing=1.15)
    box = (110, top, 970, top + len(lines) * lh + 70)
    design.rounded_card(claim, box, 40, pal.accent + (250,))
    design.text_block(claim, lines, fnt, lh, w // 2, top + 35, fill=DARK, shadow=0)
    layers.append(video.layer(claim, 0, total, **first))

    by = box[3] + 60
    left, right = (110, by, 520, by + 140), (560, by, 970, by + 140)
    for start, end in ((0, tl["reveal"]), (tl["end_in"] - 0.1, total)):  # some na revelação e volta no fim
        fx = first if start == 0 else dict(fade_in=0.3, slide=0)
        layers.append(video.layer(_button(size, left, "VERDADEIRO", GREEN), start, end, fade_out=0, **fx))
        layers.append(video.layer(_button(size, right, "FALSO", RED), start, end, fade_out=0, **fx))

    cy = min(by + 140 + 150, L["wm_y"] - 130)
    cta_img = quiz.cta_layer(size, COMMENT_CTA, cy, pal)
    layers.append(video.layer(cta_img, 0, tl["count_in"], fade_in=0, fade_out=0.2, slide=0))
    layers += quiz.countdown_layers(size, tl, cy, pal)

    true_state, false_state = ("right", "wrong") if item["is_true"] else ("wrong", "right")
    layers.append(video.layer(_button(size, left, "VERDADEIRO", GREEN, true_state), tl["reveal"], tl["end_in"],
                              fade_in=0.2, fade_out=0.3, slide=0))
    layers.append(video.layer(_button(size, right, "FALSO", RED, false_state), tl["reveal"], tl["end_in"],
                              fade_in=0.2, fade_out=0.3, slide=0))
    ans = quiz._canvas(size)
    verdict = "É VERDADE!" if item["is_true"] else "É FALSO!"
    y = design.text_block(ans, [verdict], design.font("sans_black", 64), 76, w // 2, cy - 90,
                          fill=(GREEN if item["is_true"] else RED) + (255,))
    fnt, lines, lh = design.fit(f"Certo: {item['correct']} ({item['ref_label']})", "sans_bold", 880, 200, 44, 32)
    design.text_block(ans, lines, fnt, lh, w // 2, y + 6)
    layers.append(video.layer(ans, tl["reveal"] + 0.2, tl["end_in"], fade_in=0.3, fade_out=0.3))
    layers.append(video.layer(cta_img, tl["end_in"] - 0.1, total, fade_in=0.3, slide=0))

    wm = quiz._canvas(size)
    design.watermark(wm, handle, L["wm_y"], L["wm_size"])
    layers.append(video.layer(wm, 0.0, total, fade_in=0, slide=0))
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
                    with_music, rng, **quiz.LOOP_MUSIC_FADES)
    video.poster(silent, timeline(item)["count_in"] - 0.5, out_dir / "capa.jpg")
    return {"video_music": "video_com_musica.mp4", "video_silent": "video_sem_musica.mp4",
            "poster": "capa.jpg", "images": [], "duration": total}
