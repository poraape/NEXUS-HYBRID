"""Bridge module for contextual fiscal explanations (Gemini/ChatGPT)."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable

import httpx

from core.logger import log_event
from core.settings import settings


def _offline_message(inconsistency: Dict[str, Any], context: Dict[str, Any]) -> str:
    message = inconsistency.get("message", "Inconsistência identificada")
    normative = inconsistency.get("normative_base") or "Referência normativa não informada"
    details = inconsistency.get("details") or {}
    resumo = ", ".join(f"{k}={v}" for k, v in details.items()) if details else "sem detalhes adicionais"
    segmento = context.get("segmento") or "geral"
    return f"{message}. Base: {normative}. Segmento: {segmento}. Detalhes: {resumo}."


def _call_remote(messages: Iterable[Dict[str, Any]]) -> Dict[str, str]:  # pragma: no cover - external dependency
    payload = {"messages": list(messages)}
    headers = {}
    url = "https://generative.googleapis.com/v1beta/models/gemini-pro:generateContent"
    if settings.GEMINI_API_KEY:
        headers["Authorization"] = f"Bearer {settings.GEMINI_API_KEY}"
    elif settings.OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {settings.OPENAI_API_KEY}"
        url = "https://api.openai.com/v1/chat/completions"
        payload.update({"model": "gpt-4o-mini", "temperature": 0.2})
    else:
        raise RuntimeError("Nenhuma credencial de IA configurada")
    response = httpx.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    if "candidates" in data:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    else:
        text = data["choices"][0]["message"]["content"]
    snippets = {}
    for line in text.split("\n"):
        if "::" in line:
            code, explanation = line.split("::", maxsplit=1)
            snippets[code.strip()] = explanation.strip()
    return snippets


def build_explanations(inconsistencies: Iterable[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, str]:
    if settings.OFFLINE_MODE or not (settings.GEMINI_API_KEY or settings.OPENAI_API_KEY):
        return {inc.get("code", "UNKNOWN"): _offline_message(inc, context) for inc in inconsistencies}
    try:
        messages = []
        for inc in inconsistencies:
            messages.append(
                {
                    "role": "user",
                    "content": f"Código {inc.get('code')}: {inc.get('message')} | Detalhes: {json.dumps(inc.get('details', {}), ensure_ascii=False)}",
                }
            )
        snippets = _call_remote(messages)
        return snippets
    except Exception as exc:  # pragma: no cover - fallback in offline scenarios
        log_event("ai-bridge", "WARN", "Fallback offline", {"error": str(exc)})
        return {inc.get("code", "UNKNOWN"): _offline_message(inc, context) for inc in inconsistencies}
