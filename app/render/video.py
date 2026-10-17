"""Montagem do vídeo com FFmpeg: fundo + camadas de texto animadas (fade +
deslizamento), depois a versão com música de fundo em volume baixo."""
from __future__ import annotations

import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import design

FPS = 30


@dataclass
class Layer:
    image: Image.Image
    start: float
    end: float
    fade_in: float = 0.45
    fade_out: float = 0.35
    slide: int = 36  # pixels que a camada "sobe" ao aparecer
    x: int = 0
    y: int = 0


def layer(img: Image.Image, start: float, end: float, **kw) -> Layer:
    """Cria a camada já recortada na área visível."""
    cropped, x, y = design.crop_layer(img)
    return Layer(cropped, start, end, x=x, y=y, **kw)


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou:\n{proc.stderr[-2000:]}")


def compose(background: Image.Image, layers: list[Layer], duration: float, out: Path,
            work: Path, fps: int = FPS, crf: int = 21, maxrate: str | None = None) -> None:
    """Gera o vídeo SEM música (com trilha de áudio silenciosa, para compatibilidade)."""
    work.mkdir(parents=True, exist_ok=True)
    bg_path = work / "bg.png"
    background.convert("RGB").save(bg_path)
    dur = f"{duration:.2f}"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(fps), "-t", dur,
           "-i", str(bg_path)]
    for i, lyr in enumerate(layers):
        path = work / f"layer{i:02d}.png"
        lyr.image.save(path)
        cmd += ["-loop", "1", "-framerate", str(fps), "-t", dur, "-i", str(path)]
    cmd += ["-f", "lavfi", "-t", dur, "-i", "anullsrc=r=44100:cl=stereo"]

    chains = ["[0:v]format=rgba,setsar=1[b0]"]
    for i, lyr in enumerate(layers, start=1):
        end = min(lyr.end, duration)
        fades = ["format=rgba"]
        if lyr.fade_in > 0:  # fade_in=0: a camada já entra inteira (ex.: no primeiro quadro)
            fades.append(f"fade=t=in:st={lyr.start:.2f}:d={lyr.fade_in:.2f}:alpha=1")
        if end < duration - 0.05 and lyr.fade_out > 0:
            fades.append(f"fade=t=out:st={end - lyr.fade_out:.2f}:d={lyr.fade_out:.2f}:alpha=1")
        chains.append(f"[{i}:v]{','.join(fades)}[l{i}]")
        slide_t = max(0.01, lyr.fade_in * 1.4)
        y_expr = f"{lyr.y}+{lyr.slide}*max(0\\,1-(t-{lyr.start:.2f})/{slide_t:.2f})" if lyr.slide else str(lyr.y)
        chains.append(
            f"[b{i - 1}][l{i}]overlay=x={lyr.x}:y='{y_expr}':eval=frame:"
            f"enable='between(t\\,{lyr.start:.2f}\\,{end:.2f})'[b{i}]"
        )
    chains.append(f"[b{len(layers)}]format=yuv420p[v]")
    audio_idx = len(layers) + 1
    rate = ["-maxrate", maxrate, "-bufsize", f"{int(maxrate.rstrip('k')) * 2}k"] if maxrate else []
    cmd += ["-filter_complex", ";".join(chains), "-map", "[v]", "-map", f"{audio_idx}:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), *rate, "-r", str(fps),
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-c:a", "aac", "-b:a", "96k",
            "-t", dur, "-movflags", "+faststart", str(out)]
    _run(cmd)


def add_music(silent: Path, track: Path, duration: float, volume: float, out: Path,
              rng: random.Random, fade_in: float = 1.0, fade_out: float = 1.5) -> None:
    """Versão COM música: mesma imagem, instrumental em volume baixo com fade.
    Vídeos em loop usam fades curtos para a volta ao início não ter um buraco de silêncio."""
    offset = rng.uniform(0, 6)
    fade_out_at = max(0.0, duration - fade_out)
    af = (f"[1:a]atrim=start={offset:.2f}:duration={duration:.2f},asetpts=PTS-STARTPTS,"
          f"volume={volume:.3f},afade=t=in:st=0:d={fade_in:.2f},"
          f"afade=t=out:st={fade_out_at:.2f}:d={fade_out:.2f}[a]")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-stream_loop", "-1",
          "-i", str(track), "-filter_complex", af, "-map", "0:v", "-map", "[a]",
          "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", f"{duration:.2f}",
          "-movflags", "+faststart", str(out)])


def poster(video: Path, at: float, out: Path) -> None:
    """Imagem de capa para a pré-visualização no painel."""
    _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", str(video),
          "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "4", str(out)])
