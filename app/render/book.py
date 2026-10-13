"""Template "Em qual livro está?": o versículo aparece, 4 livros como opções, contagem regressiva
e a resposta (com a referência completa). Mesmo desenho do quiz (vídeo 9:16 com música)."""
from __future__ import annotations

import random
from pathlib import Path

from . import design, quiz, video


def render(item: dict, settings: dict, out_dir: Path, seed: int, track_path: Path, rng: random.Random,
           work: Path) -> dict:
    handle = settings.get("brand", {}).get("handle", "")
    pal = design.palette_for("desafio", seed)
    silent, total, poster_at = quiz.render_video(
        item, pal, seed, handle, settings, out_dir, work, label="EM QUAL LIVRO ESTÁ?",
        hook=("1%", ["SABE EM QUAL LIVRO", "ESTÁ ESTE VERSÍCULO"]))
    with_music = out_dir / "video_com_musica.mp4"
    video.add_music(silent, track_path, total, settings.get("video", {}).get("music_volume", 0.16),
                    with_music, rng)
    video.poster(silent, poster_at, out_dir / "capa.jpg")
    return {"video_music": "video_com_musica.mp4", "video_silent": "video_sem_musica.mp4",
            "poster": "capa.jpg", "images": [], "duration": total}
