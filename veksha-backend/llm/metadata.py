"""Extract vocabulary candidates from translated phrases."""
from __future__ import annotations

import logging

from models import Patch
from llm._base import _call, _parse_json, _truncate

log = logging.getLogger(__name__)


_EXTRACT_METADATA_SYSTEM = """\
You help maintain the vocabulary of a language learner.

User message: "{user_message}"
Translation they received: "{value}"
User's existing topics: {topic_names}

Identify which words or phrases from the response the user likely does NOT know and should add
to their training vocabulary. Skip words they clearly know.

For each new word include:
- name: the word or phrase in lowercase
- context: a short fragment of the source text where it appeared (or "" if none)

Reply ONLY in JSON without markdown:
{{"patches": [{{"type": "add_word", "value": "word", "context": "..."}}, ...]}}

If there are no new words to add, return {{"patches": []}}.
"""


async def extract_metadata(user_message: str, value: str, topic_names: list[str]) -> list[Patch]:
    """Find useful vocabulary in a translated multi-word selection."""
    log.info(
        "[extract_metadata] user_message=%r value=%r topic_names=%s",
        _truncate(user_message), _truncate(value), topic_names,
    )
    system = _EXTRACT_METADATA_SYSTEM.format(
        user_message=user_message,
        value=value,
        topic_names=", ".join(topic_names) if topic_names else "(none)",
    )
    try:
        raw = await _call(system, user="", max_tokens=400, json_mode=True, call_name="extract_metadata")
        data = _parse_json(raw)
        patches = [
            Patch(
                type="add_word",
                value=str(p["value"]).strip().lower(),
                context=p.get("context", ""),
                counter=-1,
                known=False,
            )
            for p in data.get("patches", [])
            if p.get("type") == "add_word" and p.get("value")
        ]
        log.info("[extract_metadata] -> %d patch(es): %s", len(patches), [p.value for p in patches])
        return patches
    except Exception:
        log.exception("[extract_metadata] failed")
        return []
