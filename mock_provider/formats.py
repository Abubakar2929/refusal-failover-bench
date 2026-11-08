"""Exact response bodies for every mock scenario, in OpenAI, Anthropic and Gemini wire formats.

Source of truth for the refusal bodies: contracts/refusal_formats.md (copied verbatim below; the
selftest compares this module against that file so the two cannot drift apart).

Design rules
- Every non-refused answer contains the text ``ANSWERED_BY={label}``.
- A refusal scenario is served only on the API style it natively belongs to (an OpenAI
  ``finish_reason: content_filter`` has no faithful Anthropic or Gemini equivalent). Requests for a
  scenario on a non-native style get HTTP 404 with code ``scenario_not_native_to_style`` so a router
  test can never silently measure the wrong format. ``NATIVE_STYLES`` lists what is served where.
- ``ok_toolcall`` returns a call to ``write_record`` on the first model turn. Once the conversation
  contains a tool result after the last user message, it returns a final text answer instead, so an
  agent loop terminates (otherwise the agent would call the tool forever).
- Streaming is not implemented (PLAN.md 6, Objective 2). A request with ``stream: true`` (or a Gemini
  ``:streamGenerateContent`` call) gets HTTP 400 with code ``mock_streaming_not_supported``.
"""
from __future__ import annotations

import copy
import json
from typing import Any, Callable

OPENAI = "openai"
ANTHROPIC = "anthropic"
GEMINI = "gemini"
STYLES = (OPENAI, ANTHROPIC, GEMINI)

LABELS = ("mock-a", "mock-b", "mock-z")

# Scenarios whose answer is a real (non-refused) answer. Used as ground truth for "answering_model".
ANSWER_SCENARIOS = frozenset({"ok", "ok_toolcall"})

NATIVE_STYLES: dict[str, tuple[str, ...]] = {
    "ok": STYLES,
    "ok_toolcall": STYLES,
    "http500": STYLES,
    "http400_policy": (OPENAI,),
    "azure400_filter": (OPENAI,),
    "oa200_content_filter": (OPENAI,),
    "oa200_refusal_field": (OPENAI,),
    "an200_refusal": (ANTHROPIC,),
    "an200_refusal_nodetails": (ANTHROPIC,),
    "gem200_safety": (GEMINI,),
    "text_refusal": STYLES,
}

TEXT_REFUSAL = "I can't help with that."
TOOL_NAME = "write_record"
TOOL_RECORD_ID = "cust-0001"

# ---------------------------------------------------------------------------------------------
# Verbatim bodies from contracts/refusal_formats.md. "{label}" is substituted at response time.
# ---------------------------------------------------------------------------------------------
REFUSAL_BODIES: dict[str, dict[str, Any]] = {
    "oa200_content_filter": {"id": "chatcmpl-mock", "object": "chat.completion", "model": "{label}", "choices": [{"index": 0, "message": {"role": "assistant", "content": None, "refusal": None}, "finish_reason": "content_filter"}]},
    "oa200_refusal_field": {"id": "chatcmpl-mock", "object": "chat.completion", "model": "{label}", "choices": [{"index": 0, "message": {"role": "assistant", "content": None, "refusal": "I'm sorry, I cannot assist with that request."}, "finish_reason": "stop"}]},
    "http400_policy": {"error": {"code": "content_policy_violation", "message": "Your request was rejected as a result of our safety system.", "param": None, "type": "invalid_request_error"}},
    "azure400_filter": {"error": {"message": "The response was filtered due to the prompt triggering Azure OpenAI's content management policy.", "type": None, "param": "prompt", "code": "content_filter", "status": 400, "innererror": {"code": "ResponsibleAIPolicyViolation", "content_filter_result": {"violence": {"filtered": True, "severity": "medium"}}}}},
    "an200_refusal": {"id": "msg_mock", "type": "message", "role": "assistant", "model": "{label}", "content": [], "stop_reason": "refusal", "stop_details": {"type": "refusal", "category": "cyber", "explanation": "This request was declined because it could enable cyber harm."}, "usage": {"input_tokens": 12, "output_tokens": 0}},
    "an200_refusal_nodetails": {"id": "msg_mock", "type": "message", "role": "assistant", "model": "{label}", "content": [], "stop_reason": "refusal", "usage": {"input_tokens": 12, "output_tokens": 0}},
    "gem200_safety": {"candidates": [{"finishReason": "SAFETY", "index": 0, "safetyRatings": [{"category": "HARM_CATEGORY_HARASSMENT", "probability": "MEDIUM", "blocked": True}]}]},
    "text_refusal": {"id": "chatcmpl-mock", "object": "chat.completion", "model": "{label}", "choices": [{"index": 0, "message": {"role": "assistant", "content": "I can't help with that.", "refusal": None}, "finish_reason": "stop"}]},
}

OK_BODIES: dict[str, dict[str, Any]] = {
    OPENAI: {"id": "chatcmpl-mock", "object": "chat.completion", "model": "{label}", "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK ANSWERED_BY={label}", "refusal": None}, "finish_reason": "stop"}]},
    ANTHROPIC: {"id": "msg_mock", "type": "message", "role": "assistant", "model": "{label}", "content": [{"type": "text", "text": "OK ANSWERED_BY={label}"}], "stop_reason": "end_turn", "usage": {"input_tokens": 12, "output_tokens": 6}},
    GEMINI: {"candidates": [{"content": {"role": "model", "parts": [{"text": "OK ANSWERED_BY={label}"}]}, "finishReason": "STOP", "index": 0}]},
}

OK_TOOLCALL_OPENAI: dict[str, Any] = {"id": "chatcmpl-mock", "object": "chat.completion", "model": "{label}", "choices": [{"index": 0, "message": {"role": "assistant", "content": None, "refusal": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "write_record", "arguments": "{\"record_id\":\"cust-0001\",\"value\":\"ANSWERED_BY={label}\"}"}}]}, "finish_reason": "tool_calls"}]}

# Usage blocks are not in the contract for OpenAI bodies, but several clients (LiteLLM cost
# tracking, LangChain usage metadata) read them. Added only where the contract body lacks one.
OPENAI_USAGE = {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18}


def _subst(obj: Any, label: str) -> Any:
    """Replace every '{label}' inside string values (including JSON-encoded tool arguments)."""
    if isinstance(obj, str):
        return obj.replace("{label}", label)
    if isinstance(obj, list):
        return [_subst(x, label) for x in obj]
    if isinstance(obj, dict):
        return {k: _subst(v, label) for k, v in obj.items()}
    return obj


# Real Gemini responses always carry usageMetadata and modelVersion; the contract bodies omit them, and
# LiteLLM 1.108.3 raises KeyError('usageMetadata') without it (a mock artefact, not router behaviour).
GEMINI_USAGE = {"promptTokenCount": 12, "candidatesTokenCount": 6, "totalTokenCount": 18}
REALISM_KEYS = {"usage", "usageMetadata", "modelVersion"}


def _with_gemini_meta(body: dict, label: str) -> dict:
    body.setdefault("usageMetadata", dict(GEMINI_USAGE))
    body.setdefault("modelVersion", label)
    return body


def _with_openai_usage(body: dict) -> dict:
    if "usage" not in body:
        body["usage"] = dict(OPENAI_USAGE)
    return body


# ---------------------------------------------------------------------------------------------
# Error envelopes for non-OpenAI styles (http500 only; the 400 policy bodies are OpenAI/Azure-native).
# ---------------------------------------------------------------------------------------------
HTTP500_BODIES: dict[str, dict[str, Any]] = {
    OPENAI: {"error": {"message": "Internal server error.", "type": "server_error", "param": None, "code": "internal_error"}},
    ANTHROPIC: {"type": "error", "error": {"type": "api_error", "message": "Internal server error."}},
    GEMINI: {"error": {"code": 500, "message": "Internal error encountered.", "status": "INTERNAL"}},
}


def error_body(style: str, http: int, code: str, message: str) -> dict:
    """Mock-infrastructure errors (unknown scenario, wrong style, streaming) in the style's envelope."""
    if style == ANTHROPIC:
        return {"type": "error", "error": {"type": code, "message": message}}
    if style == GEMINI:
        return {"error": {"code": http, "message": message, "status": code}}
    return {"error": {"message": message, "type": "mock_error", "param": None, "code": code}}


# ---------------------------------------------------------------------------------------------
# Tool-call bodies per style
# ---------------------------------------------------------------------------------------------
def tool_args(label: str) -> dict:
    return {"record_id": TOOL_RECORD_ID, "value": f"ANSWERED_BY={label}"}


def toolcall_body(style: str, label: str) -> dict:
    if style == OPENAI:
        return _with_openai_usage(_subst(copy.deepcopy(OK_TOOLCALL_OPENAI), label))
    if style == ANTHROPIC:
        return {"id": "msg_mock", "type": "message", "role": "assistant", "model": label,
                "content": [{"type": "tool_use", "id": "toolu_mock_1", "name": TOOL_NAME, "input": tool_args(label)}],
                "stop_reason": "tool_use", "usage": {"input_tokens": 12, "output_tokens": 6}}
    return {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": TOOL_NAME, "args": tool_args(label)}}]},
                            "finishReason": "STOP", "index": 0}]}


def after_tool_body(style: str, label: str) -> dict:
    """Final answer once the tool result has been returned to the model."""
    text = f"Record written. ANSWERED_BY={label}"
    body = _subst(copy.deepcopy(OK_BODIES[style]), label)
    if style == OPENAI:
        body["choices"][0]["message"]["content"] = text
        return _with_openai_usage(body)
    if style == ANTHROPIC:
        body["content"][0]["text"] = text
        return body
    body["candidates"][0]["content"]["parts"][0]["text"] = text
    return body


def text_refusal_body(style: str, label: str) -> dict:
    if style == OPENAI:
        return _with_openai_usage(_subst(copy.deepcopy(REFUSAL_BODIES["text_refusal"]), label))
    body = _subst(copy.deepcopy(OK_BODIES[style]), label)
    if style == ANTHROPIC:
        body["content"][0]["text"] = TEXT_REFUSAL
    else:
        body["candidates"][0]["content"]["parts"][0]["text"] = TEXT_REFUSAL
    return body


# ---------------------------------------------------------------------------------------------
# Request inspection
# ---------------------------------------------------------------------------------------------
def _text_of(content: Any) -> str:
    """Flatten message content (string, list of parts/blocks) into plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                if isinstance(part.get("text"), str):
                    out.append(part["text"])
                elif "content" in part and part.get("type") != "tool_result":
                    out.append(_text_of(part["content"]))
        return "\n".join(out)
    if isinstance(content, dict):
        return _text_of(content.get("text") or content.get("parts"))
    return str(content)


def _is_tool_result_message(style: str, msg: dict) -> bool:
    if style == OPENAI:
        return msg.get("role") in ("tool", "function")
    content = msg.get("content") if style == ANTHROPIC else msg.get("parts")
    if not isinstance(content, list):
        return False
    key_type = "tool_result" if style == ANTHROPIC else None
    for part in content:
        if not isinstance(part, dict):
            continue
        if style == ANTHROPIC and part.get("type") == key_type:
            return True
        if style == GEMINI and ("functionResponse" in part or "function_response" in part):
            return True
    return False


def messages_of(style: str, body: dict) -> list[dict]:
    key = "contents" if style == GEMINI else "messages"
    msgs = body.get(key) or []
    return [m for m in msgs if isinstance(m, dict)]


def last_user_text(style: str, body: dict) -> str | None:
    """Text of the last user message that is a real user turn (not a tool-result carrier)."""
    for msg in reversed(messages_of(style, body)):
        if msg.get("role") != "user":
            continue
        if _is_tool_result_message(style, msg):
            continue
        return _text_of(msg.get("parts") if style == GEMINI else msg.get("content"))
    return None


def has_tool_result_after_last_user(style: str, body: dict) -> bool:
    for msg in reversed(messages_of(style, body)):
        if _is_tool_result_message(style, msg):
            return True
        if msg.get("role") == "user":
            return False
    return False


# ---------------------------------------------------------------------------------------------
# Main entry: scenario x style -> (status, body)
# ---------------------------------------------------------------------------------------------
def build_response(scenario: str, style: str, label: str, request_body: dict) -> tuple[int, dict]:
    status, body = _build_response(scenario, style, label, request_body)
    if style == GEMINI and status == 200:
        body = _with_gemini_meta(body, label)
    return status, body


def _build_response(scenario: str, style: str, label: str, request_body: dict) -> tuple[int, dict]:
    if scenario not in NATIVE_STYLES:
        return 404, error_body(style, 404, "unknown_scenario", f"Unknown mock scenario: {scenario}")
    if style not in NATIVE_STYLES[scenario]:
        return 404, error_body(style, 404, "scenario_not_native_to_style",
                               f"Scenario {scenario} is served only on: {', '.join(NATIVE_STYLES[scenario])}")
    if scenario == "ok":
        body = _subst(copy.deepcopy(OK_BODIES[style]), label)
        return 200, (_with_openai_usage(body) if style == OPENAI else body)
    if scenario == "ok_toolcall":
        if has_tool_result_after_last_user(style, request_body):
            return 200, after_tool_body(style, label)
        return 200, toolcall_body(style, label)
    if scenario == "http500":
        return 500, copy.deepcopy(HTTP500_BODIES[style])
    if scenario in ("http400_policy", "azure400_filter"):
        return 400, copy.deepcopy(REFUSAL_BODIES[scenario])
    if scenario == "text_refusal":
        return 200, text_refusal_body(style, label)
    body = _subst(copy.deepcopy(REFUSAL_BODIES[scenario]), label)
    return 200, (_with_openai_usage(body) if style == OPENAI else body)


def refusal_detector(style: str) -> Callable[[int, dict], bool]:
    """Ground-truth classifier used by the selftest and by agent_exp: did this response refuse?"""
    def detect(status: int, body: dict) -> bool:
        if status == 400:
            code = (body.get("error") or {}).get("code")
            return code in ("content_policy_violation", "content_filter")
        if status != 200:
            return False
        if style == OPENAI:
            choice = (body.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            return choice.get("finish_reason") == "content_filter" or bool(msg.get("refusal")) or msg.get("content") == TEXT_REFUSAL
        if style == ANTHROPIC:
            return body.get("stop_reason") == "refusal" or _text_of(body.get("content")) == TEXT_REFUSAL
        cand = (body.get("candidates") or [{}])[0]
        return cand.get("finishReason") == "SAFETY" or _text_of((cand.get("content") or {}).get("parts")) == TEXT_REFUSAL
    return detect


def contract_bodies_from_markdown(md_text: str) -> dict[str, dict]:
    """Parse contracts/refusal_formats.md into {heading: body}. Used by the selftest."""
    out: dict[str, dict] = {}
    heading = None
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("### "):
            heading = line[4:].strip()
            if heading.endswith(")") and " (HTTP " in heading:
                heading = heading.split(" (HTTP ")[0]
        elif line.strip() == "```json" and heading:
            j = i + 1
            chunk = []
            while j < len(lines) and lines[j].strip() != "```":
                chunk.append(lines[j])
                j += 1
            out[heading] = json.loads("\n".join(chunk))
            i = j
        i += 1
    return out
