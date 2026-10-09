"""Caminhos e leitura das configurações (config/settings.json + variáveis de ambiente)."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "settings.json"
CONTENT_DIR = ROOT / "content"
STATE_DIR = ROOT / "state"
ASSETS_DIR = ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
MUSIC_DIR = ASSETS_DIR / "music"

VALID_TYPES = ("verse", "quiz", "curiosity")
MAX_SLOTS = 8


def load_settings() -> dict:
    settings = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    slots = settings.get("schedule", {}).get("slots", [])
    if not 1 <= len(slots) <= MAX_SLOTS:
        raise ValueError(f"Configure de 1 a {MAX_SLOTS} horários em schedule.slots")
    for slot in slots:
        if slot.get("type") not in VALID_TYPES:
            raise ValueError(f"Tipo de post inválido: {slot.get('type')} (use {VALID_TYPES})")
    return settings


def groq_api_key() -> str | None:
    """A chave fica só em variável de ambiente / segredo do GitHub."""
    return os.environ.get("GROQ_API_KEY") or None
