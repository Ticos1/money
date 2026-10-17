"""Alerta de automação parada e de token expirando (vira uma "issue" no GitHub → e-mail).

  python -m app.health --out alerta.md [--mention seu-usuario]

Roda junto da publicação (de hora em hora). Confere:
- publicação parada: redes ligadas, mas nada publicado há mais de alerts.stalled_hours (padrão 12h),
  ou posts aprovados cujo horário passou há mais de 2h e ainda não saíram;
- geração parada: já passou das 08:00 e os posts de hoje não foram criados;
- tokens: o da Meta (vencido, inválido ou vencendo em até alerts.token_warn_days, padrão 7 dias),
  o do YouTube (renovação recusada) e a conexão do TikTok (vencendo).

Saída: 0 = tudo certo · 3 = há problema (o texto do alerta fica em --out).
A primeira linha do texto traz uma "assinatura" dos problemas: o workflow só comenta de novo
na issue aberta quando ela muda, e fecha a issue quando tudo volta ao normal.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import config, state
from .publish import scheduled_at

PROBLEM = 3
DEFAULTS = {"stalled_hours": 12, "late_hours": 2, "generate_by": "08:00", "token_warn_days": 7}
NETS = ("instagram", "facebook", "youtube", "stories", "tiktok")


def _when(text: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo("UTC"))


def check_posts(queue: list[dict], history: list[dict], settings: dict, now: datetime) -> list[tuple[str, str]]:
    """Problemas de rotina: (chave, mensagem)."""
    from .publish import applies

    cfg = {**DEFAULTS, **(settings.get("alerts") or {})}
    pub = settings.get("publishing", {})
    tz = now.tzinfo
    out: list[tuple[str, str]] = []
    today = now.date().isoformat()
    if now.strftime("%H:%M") >= cfg["generate_by"] and not any(p.get("date") == today for p in queue + history):
        out.append(("geracao", f"Os posts de hoje ({now.strftime('%d/%m')}) não foram gerados. Veja em Actions → "
                               "\"Pipeline de conteúdo\" se a execução das 05:20 falhou, ou toque em Gerar agora "
                               "no painel."))
    enabled = [n for n in NETS if pub.get(n)]
    if not enabled:
        return out
    stamps = [w for p in queue + history for v in (p.get("published") or {}).values() if v and (w := _when(v))]
    if stamps:
        last = max(stamps)
        hours = (now - last).total_seconds() / 3600
        if hours > float(cfg["stalled_hours"]):
            out.append(("parada", f"Nada foi publicado há {int(hours)} horas (último: "
                                  f"{last.astimezone(tz).strftime('%d/%m %H:%M')}). Confira se os posts estão "
                                  "aprovados no painel e se o workflow \"Publicar nas redes\" está rodando."))
    late = []
    limit = now - timedelta(hours=float(cfg["late_hours"]))
    max_attempts = int(pub.get("max_attempts", 3))
    for p in queue:
        if p.get("status") != "approved" or not (p.get("media") or {}).get("base"):
            continue
        when = scheduled_at(p, tz)
        if when > limit:
            continue
        missing = [n for n in enabled if applies(n, p, pub) and not (p.get("published") or {}).get(n)
                   and not (p.get("publish_skipped") or {}).get(n)]
        if missing:
            gave_up = [n for n in missing
                       if ((p.get("publish_errors") or {}).get(n) or {}).get("attempts", 0) >= max_attempts]
            late.append(f"{p['id']} ({p['time']}): falta {', '.join(missing)}"
                        + (f" — desistiu em {', '.join(gave_up)}" if gave_up else ""))
    if late:
        out.append(("atrasados", "Posts aprovados com o horário vencido há mais de "
                                 f"{cfg['late_hours']}h e ainda sem publicar:\n" + "\n".join(f"  - {x}" for x in late)))
    return out


def _days_left(ts: int | float | None, now: float) -> float | None:
    return None if not ts else (float(ts) - now) / 86400


def check_meta(token: str, warn_days: int, now: float) -> list[tuple[str, str]]:
    from .publishers.meta import GRAPH

    try:
        data = requests.get(f"{GRAPH}/debug_token", params={"input_token": token, "access_token": token},
                            timeout=30).json()
    except (requests.RequestException, ValueError):
        return []  # falha de rede: não é motivo para alarmar
    if "error" in data:
        err = data["error"] or {}
        if err.get("code") == 190:
            return [("token-meta", "O token da Meta (META_ACCESS_TOKEN) expirou ou foi invalidado. Gere um novo "
                                   "(docs/PUBLICACAO.md, passo 2.3) e atualize o segredo no GitHub.")]
        return []
    info = data.get("data") or {}
    if info.get("is_valid") is False:
        return [("token-meta", "O token da Meta (META_ACCESS_TOKEN) não é mais válido. Gere um novo "
                               "(docs/PUBLICACAO.md, passo 2.3) e atualize o segredo no GitHub.")]
    out = []
    left = _days_left(info.get("expires_at"), now)  # 0 = nunca expira
    if left is not None and left <= warn_days:
        out.append(("token-meta", f"O token da Meta expira em {max(0, int(left))} dia(s). Gere um token de Página "
                                  "que não expira (docs/PUBLICACAO.md, passo 2.3) e atualize META_ACCESS_TOKEN."))
    left = _days_left(info.get("data_access_expires_at"), now)
    if left is not None and left <= warn_days:
        out.append(("acesso-meta", f"O acesso aos dados da Meta vence em {max(0, int(left))} dia(s) (métricas e "
                                   "publicação podem parar). Gere o token de novo pelo Explorador da Graph API "
                                   "(docs/PUBLICACAO.md, passo 2.3)."))
    return out


def check_youtube(client_id: str, secret: str, refresh: str) -> list[tuple[str, str]]:
    try:
        data = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
            "client_id": client_id, "client_secret": secret, "refresh_token": refresh,
            "grant_type": "refresh_token"}).json()
    except (requests.RequestException, ValueError):
        return []
    if data.get("error") in ("invalid_grant", "unauthorized_client", "invalid_client"):
        return [("token-youtube", f"O YouTube recusou o acesso ({data['error']}): o refresh token venceu ou foi "
                                  "revogado. Gere outro (docs/PUBLICACAO.md, passo 3.2) e atualize YT_REFRESH_TOKEN. "
                                  "Dica: com o app do Google em modo \"Teste\", o token vence a cada 7 dias; "
                                  "publique o app para ele não vencer.")]
    return []


def check_tiktok(auth: dict, warn_days: int, now: float) -> list[tuple[str, str]]:
    left = _days_left(auth.get("refresh_expires_at"), now)
    if left is not None and left <= warn_days:
        return [("token-tiktok", f"A conexão do TikTok vence em {max(0, int(left))} dia(s). Toque em "
                                 "\"Conectar TikTok\" no painel para renovar.")]
    return []


def collect(settings: dict, now: datetime) -> list[tuple[str, str]]:
    env = os.environ.get
    cfg = {**DEFAULTS, **(settings.get("alerts") or {})}
    warn = int(cfg["token_warn_days"])
    pub = settings.get("publishing", {})
    found = check_posts(state.load_queue(), state.load_history(), settings, now)
    ts = time.time()
    if env("META_ACCESS_TOKEN") and (pub.get("instagram") or pub.get("facebook") or pub.get("stories")):
        found += check_meta(env("META_ACCESS_TOKEN"), warn, ts)
    if pub.get("youtube") and env("YT_REFRESH_TOKEN") and env("YT_CLIENT_ID") and env("YT_CLIENT_SECRET"):
        found += check_youtube(env("YT_CLIENT_ID"), env("YT_CLIENT_SECRET"), env("YT_REFRESH_TOKEN"))
    if pub.get("tiktok"):
        found += check_tiktok(state.load_tiktok_auth(), warn, ts)
    return found


def signature(found: list[tuple[str, str]]) -> str:
    keys = ",".join(sorted({k for k, _ in found}))
    return "alerta:" + hashlib.sha1(keys.encode()).hexdigest()[:10]


def text(found: list[tuple[str, str]], now: datetime, mention: str = "") -> str:
    lines = [f"<!-- {signature(found)} -->"]
    if mention:
        lines.append(f"@{mention}, a automação precisa de atenção.\n")
    lines += [f"## Verificação de {now.strftime('%d/%m/%Y %H:%M')}", ""]
    lines += [f"- {msg}" for _, msg in found]
    lines += ["", "_Esta issue fecha sozinha quando tudo voltar ao normal. "
                  "Configure em config/settings.json → alerts._"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.health")
    parser.add_argument("--out", default="alerta.md")
    parser.add_argument("--mention", default="")
    args = parser.parse_args(argv)
    settings = config.load_settings()
    now = datetime.now(ZoneInfo(settings.get("timezone", "America/Sao_Paulo")))
    found = collect(settings, now)
    if not found:
        print("Automação em dia: nada a alertar.")
        return 0
    body = text(found, now, args.mention)
    Path(args.out).write_text(body, encoding="utf-8")
    print(body)
    return PROBLEM


if __name__ == "__main__":
    sys.exit(main())
