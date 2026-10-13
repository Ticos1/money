"""Template "Complete o versículo": o versículo aparece com uma palavra faltando, 4 opções,
contagem regressiva e a resposta. Usa o mesmo desenho do quiz (vídeo 9:16 com música)."""
from __future__ import annotations

import random
from pathlib import Path

from . import design, quiz, video


def render(item: dict, settings: dict, out_dir: Path, seed: int, track_path: Path, rng: random.Random,
           work: Path) -> dict:
    handle = settings.get("brand", {}).get("handle", "")
    pal = design.palette_for("reflexao", seed)
    silent, total, poster_at = quiz.render_video(
        item, pal, seed, handle, settings, out_dir, work, label="COMPLETE O VERSÍCULO",
        hook=("90%", ["ERRA A PALAVRA QUE", "FALTA NESTE VERSÍCULO"]))
    with_music = out_dir / "video_com_musica.mp4"
    video.add_music(silent, track_path, total, settings.get("video", {}).get("music_volume", 0.16),
                    with_music, rng)
    video.poster(silent, poster_at, out_dir / "capa.jpg")
    return {"video_music": "video_com_musica.mp4", "video_silent": "video_sem_musica.mp4",
            "poster": "capa.jpg", "images": [], "duration": total}
