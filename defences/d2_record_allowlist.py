"""d2 - Refusal record + allowlist.

PLAN.md: allow fallback only for *provider* refusal kinds, only to models on APPROVED, never after a
deployer-guardrail block; attach a refusal record (who refused, kind, policy) to the follow-up call.

Flow with a `Routes` object:
  1. call with router fallback OFF (`send_no_fallback`);
  2. deployer-guardrail block (HTTP 446 / guardrail error) -> final, never re-routed;
  3. provider refusal or outage -> if the fallback route's model is in APPROVED, call it once
     (`send_fallback`) with a refusal record prepended; otherwise return the refusal;
  4. model-level text refusal -> final (the model itself declined; re-asking another model is not allowed);
  5. any answer from a model not in APPROVED -> blocked (403).
"""
from __future__ import annotations

from contracts.schemas import APPROVED, PRIMARY, RouterResult
from defences.base import Defence
from defences.d1_final import GUARDRAIL_STATUS, REFUSAL_TEXT_PATTERNS, is_outage, is_refusal, mark

DEPLOYER_GUARDRAIL_INDICATORS = ("guardrail", "deployer", "custom_guardrail")


def is_deployer_guardrail(result: RouterResult) -> bool:
    if result.http_status == GUARDRAIL_STATUS:
        return True
    return bool(result.error) and any(i in result.error.lower() for i in DEPLOYER_GUARDRAIL_INDICATORS)


def is_on_allowlist(result: RouterResult) -> bool:
    return result.reported_model in APPROVED if result.reported_model else False


def classify_refusal_kind(result: RouterResult) -> str:
    if is_deployer_guardrail(result):
        return "deployer_guardrail"
    err = (result.error or "").lower()
    for needle, kind in (("content_policy_violation", "content_policy_violation"), ("content_filter", "content_filter"),
                         ("responsibleai", "content_filter"), ("safety", "safety_filter"), ("refusal", "provider_refusal")):
        if needle in err:
            return kind
    if result.final_text and any(p.search(result.final_text) for p in REFUSAL_TEXT_PATTERNS):
        return "model_refusal"
    if result.http_status == 200 and not result.final_text:
        return "content_filter"
    return "unknown"


def refusal_record(result: RouterResult, kind: str) -> str:
    return f"[refusal-record refused_by={result.reported_model or PRIMARY} kind={kind} policy=provider-safety]"


class D2RecordAllowlist(Defence):
    name = "d2"

    def call(self, adapter, prompt: str, request_id: str, requester_token: str | None = None) -> RouterResult:
        no_fb = getattr(adapter, "send_no_fallback", adapter.send)
        result = no_fb(prompt, request_id)

        if is_refusal(result) or is_outage(result):
            kind = classify_refusal_kind(result) if is_refusal(result) else "outage"
            if kind == "deployer_guardrail":
                return mark(result, **{"x-defence": "d2-deployer-guardrail-final", "x-refusal-kind": kind})
            if kind == "model_refusal":
                return mark(result, **{"x-defence": "d2-model-refusal-final", "x-refusal-kind": kind})
            label = getattr(adapter, "fallback_label", None)
            if not hasattr(adapter, "send_fallback") or label not in APPROVED:
                return mark(result, **{"x-defence": "d2-no-approved-fallback", "x-refusal-kind": kind})
            record = refusal_record(result, kind)
            follow = adapter.send_fallback(f"{record}\n{prompt}", request_id)
            if follow.reported_model and not is_on_allowlist(follow):
                return RouterResult(http_status=403, headers={**follow.headers, "x-defence": "d2-offlist-blocked"},
                                    reported_model=follow.reported_model,
                                    error=f"Model {follow.reported_model} is not on the approved list")
            return mark(follow, **{"x-defence": "d2-provider-refusal-fallback", "x-refusal-record": record})

        if result.reported_model and not is_on_allowlist(result):
            return RouterResult(http_status=403, headers={**result.headers, "x-defence": "d2-offlist-blocked"},
                                reported_model=result.reported_model,
                                error=f"Model {result.reported_model} is not on the approved list")
        return result
