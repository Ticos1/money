"""Cliente mínimo da API da Groq (compatível com o formato da OpenAI).

- Respeita um limite diário de chamadas (config: groq.max_calls_per_day).
- Tenta o modelo principal e, se falhar, os modelos reserva.
- Qualquer erro vira GroqUnavailable: quem chama usa o banco de conteúdo.
"""
from __future__ import annotations

import json
import re
from datetime import date

import requests

API_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqUnavailable(RuntimeError):
    pass


class GroqClient:
    def __init__(self, api_key: str | None, settings: dict, usage: dict, today: date):
        cfg = settings.get("groq", {})
        self.api_key = api_key
        self.enabled = bool(cfg.get("enabled", True) and api_key)
        self.models = [cfg.get("model", "openai/gpt-oss-120b"), *cfg.get("fallback_models", [])]
        self.max_calls = int(cfg.get("max_calls_per_day", 6))
        self.today = today.isoformat()
        self.calls = usage.get("calls", 0) if usage.get("date") == self.today else 0
        self.last_model: str | None = None

    @property
    def usage(self) -> dict:
        return {"date": self.today, "calls": self.calls}

    def available(self) -> bool:
        return self.enabled and self.calls < self.max_calls

    def chat_json(self, system: str, user: str, temperature: float = 0.8) -> dict:
        """Envia o prompt e devolve o JSON da resposta (ou GroqUnavailable)."""
        if not self.available():
            raise GroqUnavailable("Groq desativada, sem chave ou limite diário atingido")
        errors = []
        for model in self.models:
            if self.calls >= self.max_calls:
                break
            body = {
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": temperature,
                "max_completion_tokens": 1500,
                "response_format": {"type": "json_object"},
            }
            if model.startswith("openai/gpt-oss"):
                body["reasoning_effort"] = "low"  # gasta menos tokens do plano grátis
            self.calls += 1
            try:
                resp = requests.post(
                    API_URL,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=body,
                    timeout=45,
                )
                if resp.status_code != 200:
                    errors.append(f"{model}: HTTP {resp.status_code} {resp.text[:200]}")
                    continue
                content = resp.json()["choices"][0]["message"]["content"]
                self.last_model = model
                return _parse_json(content)
            except (requests.RequestException, KeyError, ValueError) as exc:
                errors.append(f"{model}: {exc}")
        raise GroqUnavailable("; ".join(errors) or "limite diário atingido")


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError("resposta da Groq sem JSON")
        return json.loads(match.group())
