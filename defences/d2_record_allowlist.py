"""d2 — Refusal record + allowlist.

Allow fallback only for provider-level refusal kinds (not deployer guardrails),
only to models on APPROVED = {"mock-a", "mock-b"} (plus real approved models),
and never after a deployer-guardrail block.

Attach a refusal record (who refused, kind, policy) to the follow-up call.
"""
from __future__ import annotations

from contracts.schemas import RouterResult, APPROVED
from defences.base import Defence
from defences.d1_final import is_refusal, REFUSAL_ERROR_PATTERNS

# Deployer-guardrail indicators (status codes / error patterns)
DEPLOYER_GUARDRAIL_INDICATORS = [
    "guardrail",
    "446",  # Portkey guardrail deny status
    "deployer",
    "custom_guardrail",
]


def is_deployer_guardrail(result: RouterResult) -> bool:
    """Return True if the refusal came from a deployer guardrail, not a provider."""
    if result.error:
        lower = result.error.lower()
        for indicator in DEPLOYER_GUARDRAIL_INDICATORS:
            if indicator in lower:
                return True
    # HTTP 446 is Portkey's guardrail-deny status
    if result.http_status == 446:
        return True
    return False


def is_on_allowlist(result: RouterResult) -> bool:
    """Check if the reported model is on the approved list."""
    if result.reported_model is None:
        return False
    # Check if the reported model matches any approved model (substring match for flexibility)
    for approved in APPROVED:
        if approved in result.reported_model:
            return True
    return False


def classify_refusal_kind(result: RouterResult) -> str:
    """Classify the refusal into a kind string for the refusal record."""
    if is_deployer_guardrail(result):
        return "deployer_guardrail"
    if result.error:
        lower = result.error.lower()
        if "content_policy_violation" in lower:
            return "content_policy_violation"
        if "content_filter" in lower:
            return "content_filter"
        if "refusal" in lower:
            return "model_refusal"
        if "safety" in lower:
            return "safety_filter"
    if result.final_text and is_refusal(result):
        return "text_refusal"
    return "unknown"


class D2RecordAllowlist(Defence):
    """Refusal record + allowlist defence.

    - If a deployer guardrail refused → block (never re-route).
    - If a provider refusal → allow fallback ONLY to approved models.
    - Attach a refusal record to any follow-up.
    - If the answering model is off the allowlist → block.
    """
    name = "d2"

    def call(self, adapter, prompt: str, request_id: str,
             requester_token: str | None = None) -> RouterResult:
        result = adapter.send(prompt, request_id)

        # If it's a refusal, classify and decide
        if is_refusal(result):
            kind = classify_refusal_kind(result)

            # Deployer guardrail → never re-route
            if kind == "deployer_guardrail":
                return RouterResult(
                    final_text=result.final_text,
                    http_status=result.http_status,
                    headers={**result.headers,
                             "x-defence": "d2-deployer-guardrail-blocked",
                             "x-refusal-kind": kind},
                    reported_model=result.reported_model,
                    error=result.error,
                )

            # Provider-level refusal → return as-is (the defence layer
            # intercepts before the router can re-route)
            return RouterResult(
                final_text=result.final_text,
                http_status=result.http_status,
                headers={**result.headers,
                         "x-defence": "d2-provider-refusal-returned",
                         "x-refusal-kind": kind,
                         "x-refusal-record": f"refused_by={result.reported_model or 'unknown'}|kind={kind}"},
                reported_model=result.reported_model,
                error=result.error,
            )

        # Not a refusal — check if the answering model is on the allowlist
        if result.reported_model and not is_on_allowlist(result):
            return RouterResult(
                final_text=None,
                http_status=403,
                headers={**result.headers,
                         "x-defence": "d2-offlist-blocked",
                         "x-blocked-model": result.reported_model},
                reported_model=result.reported_model,
                error=f"Model {result.reported_model} is not on the approved list",
            )

        return result

