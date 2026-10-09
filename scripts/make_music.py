"""Compõe faixas instrumentais ORIGINAIS de fundo (estilo worship: pad, piano,
violão dedilhado) usando só matemática (numpy) + FFmpeg.

Por que gerar em vez de baixar? Faixas geradas aqui são 100% suas: não há risco
de reivindicação de direitos (Content ID) nem dependência de licença de terceiros.
Você também pode adicionar faixas do Pixabay Music ou da Biblioteca de Áudio do
YouTube em assets/music/library.json (veja docs/MUSICA.md).

Uso: python scripts/make_music.py   (gera assets/music/generated/*.m4a)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "music" / "generated"
SR = 44100
DURATION = 40.0

NOTE = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def freq(name: str, octave: int) -> float:
    midi = 12 * (octave + 1) + NOTE[name]
    return 440.0 * 2 ** ((midi - 69) / 12)


def chord(root: str, minor: bool, octave: int = 3) -> list[float]:
    r = 12 * (octave + 1) + NOTE[root]
    third = 3 if minor else 4
    return [440.0 * 2 ** ((m - 69) / 12) for m in (r - 12, r, r + third, r + 7, r + 12)]


def env_adsr(n: int, attack: float, release: float) -> np.ndarray:
    a = max(1, min(n // 2, int(attack * SR)))
    r = max(1, min(n // 2, int(release * SR)))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a) ** 2
    e[-r:] *= np.linspace(1, 0, r) ** 2
    return e


def pad_voice(f: float, n: int, brightness: float, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / SR
    out = np.zeros(n)
    for detune in (-0.07, 0.0, 0.07):  # ~±7 cents: coro suave
        ff = f * 2 ** (detune / 12)
        phase = rng.uniform(0, 2 * np.pi)
        for h in range(1, 7):
            out += (brightness ** (h - 1)) / h * np.sin(2 * np.pi * ff * h * t + phase * h)
    lfo = 1 + 0.08 * np.sin(2 * np.pi * 0.15 * t + rng.uniform(0, 6))
    return out * lfo


def piano_note(f: float, length: float, velocity: float) -> np.ndarray:
    n = int(length * SR)
    t = np.arange(n) / SR
    tone = sum((0.6 ** (h - 1)) * np.sin(2 * np.pi * f * h * t) * np.exp(-t * (1.6 + h * 0.9))
               for h in range(1, 6))
    attack = np.minimum(1, t / 0.004)
    return velocity * tone * attack


def guitar_pluck(f: float, length: float, velocity: float, rng: np.random.Generator) -> np.ndarray:
    """Karplus-Strong: corda dedilhada."""
    n = int(length * SR)
    period = max(2, int(SR / f))
    buf = rng.uniform(-1, 1, period)
    out = np.zeros(n)
    for i in range(n):
        out[i] = buf[i % period]
        buf[i % period] = 0.497 * (buf[i % period] + buf[(i + 1) % period])
    return velocity * out


def reverb(x: np.ndarray, seconds: float, rng: np.random.Generator) -> np.ndarray:
    n = int(seconds * SR)
    ir = rng.normal(0, 1, n) * np.exp(-np.linspace(0, 7, n))
    ir[0] = 0
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    wet /= np.max(np.abs(wet)) + 1e-9
    dry = x / (np.max(np.abs(x)) + 1e-9)
    return 0.55 * dry + 0.45 * wet


def lowpass(x: np.ndarray, alpha: float) -> np.ndarray:
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += alpha * (v - acc)
        y[i] = acc
    return y


def compose(spec: dict, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(DURATION * SR)
    bar = 60 / spec["bpm"] * 4
    left = np.zeros(n)
    right = np.zeros(n)

    # 1) pad com os acordes da progressão, trocando a cada compasso
    pos = 0.0
    i = 0
    while pos < DURATION:
        root, minor = spec["progression"][i % len(spec["progression"])]
        start = int(pos * SR)
        length = int(min(bar + 1.5, DURATION - pos) * SR)
        if length < SR // 2:
            break
        e = env_adsr(length, 1.2, 1.4)
        for k, f in enumerate(chord(root, minor, spec.get("octave", 3))):
            v = pad_voice(f, length, spec["brightness"], rng) * e * (0.6 if k == 0 else 0.35)
            pan = 0.5 + (k - 2) * 0.12
            left[start:start + length] += v * (1 - pan)
            right[start:start + length] += v * pan
        pos += bar
        i += 1

    # 2) melodia: piano ou violão dedilhando as notas do acorde
    step = 60 / spec["bpm"] / spec["subdiv"]
    t = spec.get("lead_in", 1.0)
    while t < DURATION - 2:
        idx = int(t // bar)
        root, minor = spec["progression"][idx % len(spec["progression"])]
        notes = chord(root, minor, spec.get("octave", 3) + 1)[1:]
        pattern = spec["pattern"]
        beat = int(round((t % bar) / step))
        note_f = notes[pattern[beat % len(pattern)] % len(notes)]
        if rng.random() < spec["density"]:
            vel = rng.uniform(0.18, 0.3)
            if spec["lead"] == "guitar":
                s = guitar_pluck(note_f, 2.5, vel, rng)
            else:
                s = piano_note(note_f, 3.0, vel)
            a = int(t * SR)
            b = min(n, a + len(s))
            pan = rng.uniform(0.35, 0.65)
            left[a:b] += s[: b - a] * (1 - pan) * spec["lead_gain"]
            right[a:b] += s[: b - a] * pan * spec["lead_gain"]
        t += step

    # 3) pulso suave para o clima de desafio (quiz)
    if spec.get("pulse"):
        beat_len = 60 / spec["bpm"]
        tt = np.arange(int(0.25 * SR)) / SR
        kick = np.sin(2 * np.pi * 55 * tt * (1 + np.exp(-tt * 30))) * np.exp(-tt * 14)
        t = 0.0
        while t < DURATION - 1:
            a = int(t * SR)
            b = min(n, a + len(kick))
            left[a:b] += kick[: b - a] * 0.25
            right[a:b] += kick[: b - a] * 0.25
            t += beat_len

    left = reverb(lowpass(left, spec["lowpass"]), 2.8, rng)
    right = reverb(lowpass(right, spec["lowpass"]), 2.8, np.random.default_rng(seed + 1))
    stereo = np.stack([left, right], axis=1)
    fade = int(2.0 * SR)
    stereo[:fade] *= np.linspace(0, 1, fade)[:, None]
    stereo[-fade:] *= np.linspace(1, 0, fade)[:, None]
    stereo /= np.max(np.abs(stereo)) + 1e-9
    return stereo * 0.85


TRACKS = [
    {"id": "gen-reflexao-1", "title": "Águas Tranquilas", "mood": "reflexao", "bpm": 64, "subdiv": 2,
     "progression": [("D", False), ("A", False), ("B", True), ("G", False)], "brightness": 0.45,
     "lead": "piano", "pattern": [0, 2, 1, 3], "density": 0.55, "lead_gain": 0.9, "lowpass": 0.12},
    {"id": "gen-reflexao-2", "title": "Lugar de Descanso", "mood": "reflexao", "bpm": 60, "subdiv": 2,
     "progression": [("C", False), ("A", True), ("F", False), ("G", False)], "brightness": 0.4,
     "lead": "guitar", "pattern": [0, 1, 2, 3, 2, 1], "density": 0.7, "lead_gain": 0.8, "lowpass": 0.1},
    {"id": "gen-alegria-1", "title": "Manhã de Graça", "mood": "alegria", "bpm": 84, "subdiv": 2,
     "progression": [("G", False), ("C", False), ("E", True), ("D", False)], "brightness": 0.55,
     "lead": "guitar", "pattern": [0, 1, 2, 1, 3, 1, 2, 1], "density": 0.9, "lead_gain": 1.0, "lowpass": 0.16},
    {"id": "gen-alegria-2", "title": "Celebrar", "mood": "alegria", "bpm": 78, "subdiv": 2,
     "progression": [("E", False), ("B", False), ("C#", True), ("A", False)], "brightness": 0.55,
     "lead": "piano", "pattern": [0, 2, 3, 2], "density": 0.8, "lead_gain": 0.9, "lowpass": 0.15},
    {"id": "gen-desafio-1", "title": "Contagem", "mood": "desafio", "bpm": 92, "subdiv": 2,
     "progression": [("A", True), ("F", False), ("C", False), ("G", False)], "brightness": 0.5,
     "lead": "piano", "pattern": [0, 1, 2, 1], "density": 0.75, "lead_gain": 0.8, "lowpass": 0.14,
     "pulse": True},
    {"id": "gen-desafio-2", "title": "Será Que Você Sabe?", "mood": "desafio", "bpm": 96, "subdiv": 2,
     "progression": [("E", True), ("C", False), ("G", False), ("D", False)], "brightness": 0.5,
     "lead": "guitar", "pattern": [0, 2, 1, 3], "density": 0.8, "lead_gain": 0.8, "lowpass": 0.14,
     "pulse": True},
]


def write_wav(path: Path, stereo: np.ndarray) -> None:
    data = (stereo * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    with tempfile.TemporaryDirectory() as tmp:
        for seed, spec in enumerate(TRACKS, start=7):
            wav = Path(tmp) / f"{spec['id']}.wav"
            write_wav(wav, compose(spec, seed))
            out = OUT / f"{spec['id']}.m4a"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                            "-c:a", "aac", "-b:a", "128k", str(out)], check=True)
            entries.append({
                "id": spec["id"], "title": spec["title"], "mood": spec["mood"],
                "file": f"generated/{spec['id']}.m4a",
                "source": "Composição original gerada por scripts/make_music.py",
                "license": "Própria (domínio público / CC0)", "url": "",
            })
            print("ok", out.name, file=sys.stderr)
    print(json.dumps(entries, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
