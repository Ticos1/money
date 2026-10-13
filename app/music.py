"""Biblioteca de músicas de fundo (livres de direitos) e sugestões gospel.

- Vídeo "com música": usa uma faixa da biblioteca (assets/music/library.json),
  escolhida pelo clima do post e em rodízio para não repetir sempre a mesma.
- Vídeo "sem música": para você colocar uma música gospel da biblioteca do
  próprio app (TikTok/Kwai/Instagram), que é licenciada pela plataforma.
"""
from __future__ import annotations

import json
import random

from .config import CONTENT_DIR, MUSIC_DIR

MOOD_BY_TYPE = {"quiz": "desafio", "curiosity": "alegria", "fill": "reflexao", "truefalse": "desafio"}


def load_library() -> list[dict]:
    data = json.loads((MUSIC_DIR / "library.json").read_text(encoding="utf-8"))
    tracks = []
    for t in data["tracks"]:
        if t.get("enabled", True) and (MUSIC_DIR / t["file"]).exists():
            tracks.append(t)
    return tracks


def pick_track(mood: str, recent_ids: list[str], rng: random.Random) -> dict:
    tracks = load_library()
    if not tracks:
        raise RuntimeError("Nenhuma faixa em assets/music/library.json (rode scripts/make_music.py)")
    same = [t for t in tracks if t["mood"] == mood] or tracks
    fresh = [t for t in same if t["id"] not in recent_ids[-3:]] or same
    return rng.choice(fresh)


def gospel_suggestions(mood: str, tags: list[str], rng: random.Random, count: int = 3) -> list[dict]:
    data = json.loads((CONTENT_DIR / "gospel_suggestions.json").read_text(encoding="utf-8"))
    songs = data["songs"]
    want_mood = "alegria" if mood == "desafio" else mood

    def score(song: dict) -> float:
        s = 2.0 * len(set(song.get("themes", [])) & set(tags))
        s += 1.0 if want_mood in song.get("moods", []) or mood in song.get("moods", []) else 0
        return s + rng.random()  # desempate aleatório para variar

    best = sorted(songs, key=score, reverse=True)[:count]
    return [{"title": s["title"], "artist": s["artist"]} for s in best]
