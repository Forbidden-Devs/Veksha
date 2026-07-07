"""
llm/_base.py — base OpenAI HTTP client and shared helpers.
"""
from __future__ import annotations

import logging

import aiohttp

from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_SMART_MODEL

log = logging.getLogger(__name__)

_API_URL = "https://api.openai.com/v1/chat/completions"

_LANG_NAMES: dict[str, str] = {
    "en": "English", "ru": "Russian", "tr": "Turkish", "de": "German",
    "fr": "French", "es": "Spanish", "it": "Italian", "pt": "Portuguese",
    "pl": "Polish", "uk": "Ukrainian", "ar": "Arabic", "he": "Hebrew",
    "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "hi": "Hindi",
    "nl": "Dutch", "sv": "Swedish", "fi": "Finnish", "cs": "Czech",
    "el": "Greek", "ka": "Georgian", "vi": "Vietnamese", "th": "Thai",
    "id": "Indonesian",
}

_REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _is_reasoning_model(model: str) -> bool:
    return model.startswith(_REASONING_MODEL_PREFIXES)


def _native_lang_note(native_lang: str) -> str:
    name = _LANG_NAMES.get(native_lang or "en", native_lang or "English")
    return (
        f"\n\nIMPORTANT: Communicate with the user in {name}. "
        f"Use {name} for ALL explanations, tasks, feedback, and error messages."
    )


def _headers() -> dict:
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Set the environment variable: export OPENAI_API_KEY=sk-..."
        )
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }


def _truncate(s: str, limit: int = 500) -> str:
    s = s or ""
    return s if len(s) <= limit else s[:limit] + f"...[+{len(s) - limit} chars]"


def _clean_json(raw: str) -> str:
    return raw.replace("```json", "").replace("```", "").strip()


import json as _json
_decoder = _json.JSONDecoder()


def _parse_json(raw: str) -> dict:
    """Parse the first valid JSON object from a raw LLM response.

    Models occasionally emit duplicate objects or trailing garbage; raw_decode()
    stops at the end of the first complete JSON value instead of failing on the rest.
    """
    cleaned = _clean_json(raw)
    obj, _ = _decoder.raw_decode(cleaned)
    return obj


async def _call(
    system: str,
    user: str | None = None,
    messages: list[dict] | None = None,
    max_tokens: int = 512,
    temp: float = 0.0,
    json_mode: bool = False,
    call_name: str = "_call",
    model: str | None = None,
) -> str:
    """
    Base Chat Completions call.

    Pass either `user` (single message) or `messages` (dialog history).
    Specify `model` to override OPENAI_MODEL (e.g. use OPENAI_SMART_MODEL for
    content generation).
    For GPT-5.x / o-series models: "max_tokens" → "max_completion_tokens",
    "temperature" omitted (these models reject non-default values with HTTP 400).
    """
    resolved_model = model or OPENAI_MODEL

    chat_messages = [{"role": "system", "content": system}]
    if messages is not None:
        chat_messages += messages
    else:
        chat_messages.append({"role": "user", "content": user or ""})

    reasoning_model = _is_reasoning_model(resolved_model)

    payload: dict = {"model": resolved_model, "messages": chat_messages}
    if reasoning_model:
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["max_tokens"] = max_tokens
        payload["temperature"] = temp

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    log.debug(
        "[LLM] -> %s | model=%s max_tokens=%d temp=%s json_mode=%s reasoning=%s | system=%r | last=%r",
        call_name, resolved_model, max_tokens, temp, json_mode, reasoning_model,
        _truncate(system), _truncate(chat_messages[-1].get("content", "")),
    )

    async with aiohttp.ClientSession() as s:
        async with s.post(_API_URL, json=payload, headers=_headers()) as r:
            if r.status >= 400:
                log.error("[LLM] <- %s | HTTP %d | body=%s", call_name, r.status, _truncate(await r.text(), 1000))
            r.raise_for_status()
            data = await r.json()
            content = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            log.info(
                "[LLM] <- %s | model=%s tokens(prompt=%s completion=%s total=%s) | response=%r",
                call_name, resolved_model,
                usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens"),
                _truncate(content),
            )
            return content
