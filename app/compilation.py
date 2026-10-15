"""Vídeo longo (~10 min) com várias perguntas de quiz, para o YouTube (formato 16:9).

Como funciona:
  1. escolhe as perguntas: primeiro os quizzes dos últimos dias (já validados na
     Bíblia) e, se faltar, completa com quizzes novos do banco;
  2. cada pergunta vira um clipe horizontal (pergunta → alternativas → contagem →
     resposta), montado com FFmpeg como os Reels;
  3. junta introdução + clipes + encerramento, coloca música de fundo e cria a
     miniatura e a descrição com capítulos (0:00, 0:07, ...).

É gerado uma vez por semana (config/settings.json → compilation) ou pelo botão do
painel, e publicado só no YouTube como vídeo normal (não é Short).
"""
from __future__ import annotations

import random
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from . import bible, config, music, state, validate, youtube_seo
from .publish import publish_at
from .render import cover, design, quiz, video

KIND = "compilation"
SIZE = (1280, 720)
FPS = 24
CRF = 28
MAXRATE = "700k"          # ~50 MB para 10 min: cabe no GitHub (limite de 100 MB por arquivo)
INTRO_S, OUTRO_S = 7.0, 9.0
RECENT_POST_DAYS = 14     # quizzes dos últimos dias entram primeiro
NO_REPEAT_DAYS = 90       # uma pergunta não volta a uma compilação por 90 dias
TAGS = ["quizbiblico", "biblia", "perguntasbiblicas", "desafiobiblico", "evangelico", "fe", "jesus"]


# ---------- escolha das perguntas
def clip_timeline(item: dict) -> dict:
    read = min(6.5, max(3.0, (len(item["question"]) + sum(len(o) for o in item["options"])) / 22))
    opts_in = [0.8 + 0.25 * i for i in range(4)]
    count_in = opts_in[-1] + 0.4 + read
    count = 5
    reveal = count_in + count
    return {"q_in": 0.3, "opts_in": opts_in, "count_in": count_in, "count": count,
            "reveal": reveal, "total": round(reveal + 3.5, 2)}


def _recent_quizzes(today: date) -> list[dict]:
    """Quizzes publicados (ou na fila) nos últimos dias, com conteúdo já validado."""
    limit = (today - timedelta(days=RECENT_POST_DAYS)).isoformat()
    out = []
    for post in state.load_queue() + state.load_history():
        if post.get("type") != "quiz" or post.get("date", "") < limit or post.get("status") == "rejected":
            continue
        try:
            item = validate.validate("quiz", dict(post["content"]))
        except (validate.ContentError, bible.BibleError, KeyError, TypeError):
            continue
        out.append({**item, "source": "recent"})
    return out


def pick_quizzes(today: date, used: dict, rng: random.Random, target_s: float,
                 log: list[str]) -> tuple[list[dict], dict]:
    """Devolve (perguntas escolhidas, atualizações para used.json)."""
    stamp = today.isoformat()
    cutoff = (today - timedelta(days=NO_REPEAT_DAYS)).isoformat()
    done = {k for k, d in used.get("compilation", {}).items() if d >= cutoff}
    budget = target_s - INTRO_S - OUTRO_S
    chosen: list[dict] = []
    keys: set[str] = set()
    total = 0.0

    def add(item: dict) -> bool:
        nonlocal total
        if item["ref_key"] in keys or item["ref_key"] in done:
            return False
        length = clip_timeline(item)["total"]
        if chosen and total + length > budget + 6:
            return False
        chosen.append(item)
        keys.add(item["ref_key"])
        total += length
        return True

    recent = _recent_quizzes(today)
    rng.shuffle(recent)
    for item in recent:
        add(item)

    updates: dict = {"compilation": {}}
    bank = []
    for raw in validate.load_bank("quiz"):
        try:
            bank.append({**validate.validate("quiz", raw), "source": "bank"})
        except (validate.ContentError, bible.BibleError):
            continue
    recent_refs = {k for k, d in used.get("refs", {}).items()
                   if d >= (today - timedelta(days=180)).isoformat()}
    pool = [i for i in bank if i["id"] not in used.get("quiz", {}) and i["ref_key"] not in recent_refs]
    rng.shuffle(pool)
    spare = [i for i in bank if i not in pool]  # já usados: só se o banco novo acabar
    rng.shuffle(spare)
    for item in pool + spare:
        if total >= budget:
            break
        if add(item) and item in pool:
            updates.setdefault("quiz", {})[item["id"]] = stamp
            updates.setdefault("refs", {})[item["ref_key"]] = stamp
    if total < budget * 0.8:
        log.append(f"compilação com poucas perguntas ({len(chosen)}): o banco de quizzes está curto")
    rng.shuffle(chosen)
    updates["compilation"] = {i["ref_key"]: stamp for i in chosen}
    return chosen, updates


# ---------- renderização
def _canvas() -> Image.Image:
    return quiz._canvas(SIZE)


def render_clip(item: dict, n: int, total_n: int, seed: int, handle: str, out: Path, work: Path) -> float:
    w, h = SIZE
    L = quiz.LAYOUTS[SIZE]
    pal = design.palette_for("desafio", seed)
    tl = clip_timeline(item)
    total = tl["total"]
    bg = design.background(w, h, pal, seed)
    layers = [video.Layer(design.bokeh(w, h, pal, seed + 1, count=12), 0, total, fade_in=1.0, slide=0)]

    lab = _canvas()
    design.label(lab, f"DESAFIO BÍBLICO · PERGUNTA {n}/{total_n}", L["label_y"], L["label_size"], pal.accent)
    layers.append(video.layer(lab, 0.0, total, fade_in=0.3, slide=0))

    geo = quiz._geometry(SIZE, item)
    layers.append(video.layer(quiz._question_layer(SIZE, item, geo), tl["q_in"], total, slide=30))
    for i in range(4):
        layers.append(video.layer(quiz._option_layer(SIZE, item, geo, i, pal), tl["opts_in"][i], total,
                                  fade_in=0.25, slide=20))

    cy = min(max(geo["end"] + 58, 590), 628)
    for k in range(tl["count"]):
        c = _canvas()
        d = design.ImageDraw.Draw(c)
        r = 40
        d.ellipse([w // 2 - r, cy - r, w // 2 + r, cy + r], outline=pal.accent + (255,), width=6,
                  fill=(0, 0, 0, 90))
        d.text((w // 2, cy + 2), str(tl["count"] - k), font=design.font("sans_black", 50),
               fill=(255, 255, 255, 255), anchor="mm")
        start = tl["count_in"] + k
        layers.append(video.layer(c, start, start + 1.0, fade_in=0.1, fade_out=0.1, slide=0))

    for i in range(4):
        state_ = "correct" if i == item["answer"] else "dim"
        layers.append(video.layer(quiz._option_layer(SIZE, item, geo, i, pal, state_), tl["reveal"], total,
                                  fade_in=0.25, slide=0))
    ans = _canvas()
    design.text_block(ans, [f"RESPOSTA: {quiz.LETTERS[item['answer']]}  ·  {item['ref_label']}"],
                      design.font("sans_black", 40), 52, w // 2, cy - 30, fill=pal.accent + (255,))
    layers.append(video.layer(ans, tl["reveal"] + 0.2, total, fade_in=0.3))

    wm = _canvas()
    design.watermark(wm, handle, L["wm_y"], L["wm_size"])
    layers.append(video.layer(wm, 0.0, total, fade_in=0.01, slide=0))
    video.compose(bg, layers, total, out, work, fps=FPS, crf=CRF, maxrate=MAXRATE)
    return total


def render_intro(total_n: int, minutes: int, seed: int, handle: str, out: Path, work: Path) -> float:
    w, h = SIZE
    pal = design.palette_for("desafio", seed)
    bg = design.background(w, h, pal, seed)
    c = _canvas()
    design.text_block(c, ["SÓ 1% ACERTA"], design.font("sans_black", 130), 150, w // 2, 150,
                      fill=pal.accent + (255,))
    design.text_block(c, [f"TODAS AS {total_n} PERGUNTAS DA BÍBLIA"], design.font("sans_black", 46), 60,
                      w // 2, 350)
    fnt, lines, lh = design.fit("Pause, anote suas respostas e veja quantas você acerta!", "sans_bold",
                                900, 130, 38, 28)
    design.text_block(c, lines, fnt, lh, w // 2, 450)
    layers = [video.Layer(design.bokeh(w, h, pal, seed + 1, count=12), 0, INTRO_S, fade_in=0.8, slide=0),
              video.layer(c, 0.2, INTRO_S, fade_in=0.5, slide=40)]
    wm = _canvas()
    design.watermark(wm, handle, quiz.LAYOUTS[SIZE]["wm_y"], quiz.LAYOUTS[SIZE]["wm_size"])
    layers.append(video.layer(wm, 0, INTRO_S, fade_in=0.01, slide=0))
    video.compose(bg, layers, INTRO_S, out, work, fps=FPS, crf=CRF, maxrate=MAXRATE)
    return INTRO_S


def render_outro(seed: int, handle: str, out: Path, work: Path) -> float:
    w, h = SIZE
    pal = design.palette_for("desafio", seed)
    bg = design.background(w, h, pal, seed)
    c = _canvas()
    design.text_block(c, ["Quantas você acertou?"], design.font("serif_bold", 84), 110, w // 2, 190,
                      fill=pal.accent + (255,))
    fnt, lines, lh = design.fit("Conte nos comentários e desafie um amigo!", "sans_bold", 900, 130, 46, 30)
    y = design.text_block(c, lines, fnt, lh, w // 2, 340)
    if handle:
        design.text_block(c, [f"Inscreva-se e siga {handle}"], design.font("sans_bold", 40), 54, w // 2, y + 40)
    layers = [video.Layer(design.bokeh(w, h, pal, seed + 1, count=12), 0, OUTRO_S, fade_in=0.8, slide=0),
              video.layer(c, 0.2, OUTRO_S, fade_in=0.5, slide=40, fade_out=0.6)]
    video.compose(bg, layers, OUTRO_S, out, work, fps=FPS, crf=CRF, maxrate=MAXRATE)
    return OUTRO_S


def render_thumbnail(total_n: int, minutes: int, seed: int, handle: str, out: Path) -> None:
    cover.long_cover(total_n, minutes, seed, handle, out)


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def concat(clips: list[Path], out: Path, work: Path) -> None:
    listing = work / "lista.txt"
    listing.write_text("".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8")
    video._run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                "-c", "copy", str(out)])


def add_long_music(silent: Path, duration: float, volume: float, out: Path, rng: random.Random) -> None:
    """Música de fundo: várias faixas da biblioteca em sequência, com fade em cada uma."""
    tracks = [t for t in music.load_library() if t["mood"] in ("desafio", "alegria")] or music.load_library()
    files: list[tuple[Path, float]] = []
    covered = 0.0
    order: list[dict] = []
    while covered < duration:
        batch = tracks[:]
        rng.shuffle(batch)
        if order and len(batch) > 1 and batch[0] is order[-1]:
            batch.append(batch.pop(0))
        for t in batch:
            path = config.MUSIC_DIR / t["file"]
            length = _ffprobe_duration(path)
            files.append((path, length))
            order.append(t)
            covered += length
            if covered >= duration:
                break
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent)]
    parts = []
    for i, (path, length) in enumerate(files, start=1):
        cmd += ["-i", str(path)]
        parts.append(f"[{i}:a]afade=t=in:st=0:d=1.2,afade=t=out:st={max(0.0, length - 1.2):.2f}:d=1.2[a{i}]")
    chain = "".join(f"[a{i}]" for i in range(1, len(files) + 1))
    parts.append(f"{chain}concat=n={len(files)}:v=0:a=1,atrim=duration={duration:.2f},volume={volume:.3f},"
                 f"afade=t=out:st={max(0.0, duration - 2):.2f}:d=2[a]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[a]", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "96k", "-t", f"{duration:.2f}", "-movflags", "+faststart", str(out)]
    video._run(cmd)


def _stamp(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def youtube_captions(total_n: int, minutes: int, chapters: list[tuple[float, str]], handle: str) -> dict:
    title = youtube_seo.long_title(total_n, minutes)
    lines = "\n".join(f"{_stamp(t)} {name}" for t, name in chapters)
    follow = f"Inscreva-se no canal e siga {handle} para mais." if handle else "Inscreva-se no canal para mais."
    desc = (f"Você conhece mesmo a Bíblia? Responda {total_n} perguntas neste desafio de {minutes} minutos!\n"
            "Pause, anote suas respostas e confira cada resposta logo depois da contagem regressiva.\n\n"
            f"Capítulos:\n{lines}\n\n"
            "Quantas você acertou? Conte nos comentários!\n\n"
            f"{follow}\nTexto bíblico: {bible.TRANSLATION_NAME} (domínio público).\n\n"
            + " ".join(f"#{t}" for t in TAGS))
    return {"title": title[:100], "description": desc[:4900], "tags": youtube_seo.tags(KIND)}


# ---------- montagem completa
def build_post(today: date, settings: dict, used: dict, media_root: Path, post_id: str, slot: int,
               log: list[str], seed_text: str | None = None) -> tuple[dict, dict]:
    """Gera o vídeo longo e devolve (post para a fila, atualizações do used.json)."""
    import hashlib
    comp = settings.get("compilation", {})
    minutes = max(3, min(20, int(comp.get("minutes", 10))))
    handle = settings.get("brand", {}).get("handle", "")
    seed = int(hashlib.sha1((seed_text or post_id).encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    items, updates = pick_quizzes(today, used, rng, minutes * 60, log)
    if len(items) < 3:
        raise RuntimeError("poucas perguntas para montar o vídeo longo")
    day = today.isoformat()
    out_dir = media_root / day / post_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    work = out_dir.parent / f".work-{post_id}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    try:
        n = len(items)
        parts: list[Path] = []
        p = work / "intro.mp4"
        render_intro(n, minutes, seed, handle, p, work / "w-intro")
        parts.append(p)
        for i, item in enumerate(items, start=1):
            p = work / f"q{i:02d}.mp4"
            render_clip(item, i, n, seed + i * 7, handle, p, work / f"w{i:02d}")
            parts.append(p)
            shutil.rmtree(work / f"w{i:02d}", ignore_errors=True)
        p = work / "outro.mp4"
        render_outro(seed + 999, handle, p, work / "w-outro")
        parts.append(p)
        durations = [_ffprobe_duration(x) for x in parts]  # tempos reais, para os capítulos
        joined = work / "junto.mp4"
        concat(parts, joined, work)
        total = _ffprobe_duration(joined)
        final = out_dir / "video_longo.mp4"
        add_long_music(joined, total, float(settings.get("video", {}).get("music_volume", 0.16)) * 0.8, final, rng)
        render_thumbnail(n, minutes, seed, handle, out_dir / "miniatura.jpg")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    # capítulos com os tempos reais de cada clipe (a última pergunta vai até o fim)
    chapters = [(0.0, "Introdução")]
    t = durations[0]
    for i in range(1, n + 1):
        chapters.append((t, f"Pergunta {i}"))
        t += durations[i]
    yt = youtube_captions(n, round(total / 60), chapters, handle)
    tz = ZoneInfo(settings.get("timezone", "America/Sao_Paulo"))
    slot_time = comp.get("time", "18:00")
    auto = settings.get("approval", {}).get("auto_approve", False)
    status = "approved" if auto else "pending"
    when = publish_at(post_id, day, slot_time, settings)
    if auto and datetime.fromisoformat(when).replace(tzinfo=tz) <= datetime.now(tz):
        status = "pending"
        log.append("horário já passou: aguardando você (aprovar ou Publicar agora)")
    post = {
        "id": post_id, "date": day, "slot": slot, "time": slot_time,
        "publish_at": when, "type": KIND, "status": status,
        "created_at": datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds"),
        "source": "bank", "bank_id": None, "model": None,
        "content": {"title": yt["title"], "count": n, "duration": round(total),
                    "questions": [{"n": i, "question": it["question"], "ref_label": it["ref_label"]}
                                  for i, it in enumerate(items, start=1)]},
        "captions": {"youtube": yt},
        "caption_source": "template",
        "music": None, "gospel_suggestions": [],
        "media": {"base": f"media/{day}/{post_id}/", "version": 1, "video_music": "video_longo.mp4",
                  "poster": "miniatura.jpg", "thumbnail": "miniatura.jpg", "images": [],
                  "duration": round(total, 1), "long": True},
        "published": {p: None for p in state.PLATFORMS},
        "log": log, "error": None,
    }
    return post, updates
