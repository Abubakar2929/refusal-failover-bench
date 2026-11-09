"""d1 - Refusals are final.

PLAN.md: call the router with fallback disabled; if any refusal kind is detected (provider refusal, model
refusal, or deployer-guardrail block), return it. Only outages (HTTP 5xx, timeouts/transport errors) may
fall back.

With a `Routes` object (defences/routes.py) the call goes to `send_no_fallback`; an outage then goes to
`send_fallback`. With a plain adapter (no route set) it degrades to a single call and never retries.
"""
from __future__ import annotations

import re

from contracts.schemas import RouterResult
from defences.base import Defence

REFUSAL_TEXT_PATTERNS = [
    re.compile(r"I can'?t help with that", re.IGNORECASE),
    re.compile(r"I'?m sorry,? I cannot assist", re.IGNORECASE),
    re.compile(r"I'?m unable to (?:help|assist|provide)", re.IGNORECASE),
    re.compile(r"I (?:cannot|can'?t) (?:assist|help|provide|fulfill)", re.IGNORECASE),
    re.compile(r"against (?:my|our) (?:policy|guidelines)", re.IGNORECASE),
    re.compile(r"not (?:able|allowed) to", re.IGNORECASE),
    re.compile(r"(?:content|safety) (?:policy|filter)", re.IGNORECASE),
]
REFUSAL_ERROR_PATTERNS = [
    re.compile(r"content_policy_violation", re.IGNORECASE),
    re.compile(r"content_filter", re.IGNORECASE),
    re.compile(r"refusal", re.IGNORECASE),
    re.compile(r"ResponsibleAI", re.IGNORECASE),
    re.compile(r"SAFETY", re.IGNORECASE),
    re.compile(r"guardrail", re.IGNORECASE),
]
GUARDRAIL_STATUS = 446  # Portkey deny (routers/portkey_adapter.py)


def is_refusal(result: RouterResult) -> bool:
    """True if the result is any kind of 'no': guardrail block, provider refusal or model refusal."""
    if result.http_status == GUARDRAIL_STATUS:
        return True
    if result.error and any(p.search(result.error) for p in REFUSAL_ERROR_PATTERNS):
        return True
    if result.final_text and any(p.search(result.final_text) for p in REFUSAL_TEXT_PATTERNS):
        return True
    # 200 with no content (e.g. finish_reason content_filter / Gemini SAFETY) is a refusal.
    if result.http_status == 200 and not result.final_text:
        return True
    return False


def is_outage(result: RouterResult) -> bool:
    """Transport error / timeout (status 0) or a 5xx that is not a refusal."""
    return (result.http_status == 0 or result.http_status >= 500) and not is_refusal(result)


def mark(result: RouterResult, **headers) -> RouterResult:
    return result.model_copy(update={"headers": {**result.headers, **headers}})


class D1Final(Defence):
    name = "d1"

    def call(self, adapter, prompt: str, request_id: str, requester_token: str | None = None) -> RouterResult:
        no_fb = getattr(adapter, "send_no_fallback", adapter.send)
        result = no_fb(prompt, request_id)
        if is_refusal(result):
            return mark(result, **{"x-defence": "d1-refusal-final"})
        if is_outage(result) and hasattr(adapter, "send_fallback"):
            return mark(adapter.send_fallback(prompt, request_id), **{"x-defence": "d1-outage-fallback"})
        return result
