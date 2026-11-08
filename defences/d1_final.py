"""d1 — Refusals are final.

Detect any refusal kind in the response and return it as-is — never allow
fallback to retry on a refusal. Only true outages (http 500 / timeouts)
should trigger fallback.

Implementation: We call the adapter once. If the response looks like a
refusal (any detected pattern), we return it immediately. We do NOT retry
or re-route.
"""
from __future__ import annotations

import re

from contracts.schemas import RouterResult
from defences.base import Defence

# Patterns that indicate a refusal (match against final_text and error fields)
REFUSAL_TEXT_PATTERNS = [
    re.compile(r"I can'?t help with that", re.IGNORECASE),
    re.compile(r"I'?m sorry,? I cannot assist", re.IGNORECASE),
    re.compile(r"I'?m unable to (?:help|assist|provide)", re.IGNORECASE),
    re.compile(r"I (?:cannot|can'?t) (?:assist|help|provide|fulfill)", re.IGNORECASE),
    re.compile(r"against (?:my|our) (?:policy|guidelines)", re.IGNORECASE),
    re.compile(r"not (?:able|allowed) to", re.IGNORECASE),
    re.compile(r"(?:content|safety) (?:policy|filter)", re.IGNORECASE),
]

# Error-field patterns that indicate provider/platform refusal
REFUSAL_ERROR_PATTERNS = [
    re.compile(r"content_policy_violation", re.IGNORECASE),
    re.compile(r"content_filter", re.IGNORECASE),
    re.compile(r"refusal", re.IGNORECASE),
    re.compile(r"ResponsibleAI", re.IGNORECASE),
    re.compile(r"SAFETY", re.IGNORECASE),
]


def is_refusal(result: RouterResult) -> bool:
    """Return True if the result looks like any kind of refusal."""
    # Check error field
    if result.error:
        for pat in REFUSAL_ERROR_PATTERNS:
            if pat.search(result.error):
                return True

    # Check final_text
    if result.final_text:
        for pat in REFUSAL_TEXT_PATTERNS:
            if pat.search(result.final_text):
                return True

    # A null final_text with a non-server-error status might be a 200-OK refusal
    # (content_filter with null content). Only flag if the error hints at a filter.
    if result.final_text is None and result.http_status == 200 and result.error:
        return True

    return False


class D1Final(Defence):
    """Refusals are final — any detected refusal is returned as-is, blocking re-route."""
    name = "d1"

    def call(self, adapter, prompt: str, request_id: str,
             requester_token: str | None = None) -> RouterResult:
        result = adapter.send(prompt, request_id)

        if is_refusal(result):
            # Mark as a refusal — never re-route
            return RouterResult(
                final_text=result.final_text,
                http_status=result.http_status,
                headers={**result.headers, "x-defence": "d1-refusal-final"},
                reported_model=result.reported_model,
                error=result.error,
            )

        return result

