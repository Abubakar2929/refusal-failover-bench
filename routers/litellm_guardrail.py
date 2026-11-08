"""LiteLLM proxy custom guardrail: pre-call block of requests matching routers/guardrail_policy.py.

litellm 1.108.3: base class integrations/custom_guardrail.py:337; the proxy calls async_pre_call_hook from
proxy/utils.py:2376-2377 after should_run_guardrail (proxy/utils.py:2471).
"""
from fastapi import HTTPException
from litellm.integrations.custom_guardrail import CustomGuardrail

from routers.guardrail_policy import BLOCK_MARKER, is_blocked

BLOCK_STATUS = 446  # Same status as Portkey's deny, which routers/runner.py reads as a guardrail block.


def message_text(data: dict) -> str:
    """Return the text of every message in the request; list content keeps its text parts only."""
    parts = []
    for message in data.get("messages") or []:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(p.get("text", "") for p in content if isinstance(p, dict))
    return "\n".join(parts)


class PolicyGuardrail(CustomGuardrail):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        if is_blocked(message_text(data)):
            raise HTTPException(status_code=BLOCK_STATUS, detail={"error": BLOCK_MARKER})
        return data
