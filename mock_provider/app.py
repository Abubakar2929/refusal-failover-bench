"""Mock LLM provider serving every refusal scenario in OpenAI, Anthropic and Gemini wire formats.

Run:  uvicorn mock_provider.app:app --port 8900

URL scheme (PLAN.md 4.1) -- the model label and the scenario are in the path:
    POST /p/{label}/{scenario_id}/v1/chat/completions                       (OpenAI style)
    POST /p/{label}/{scenario_id}/v1/messages                               (Anthropic style)
    POST /p/{label}/{scenario_id}/v1beta/models/{model}:generateContent     (Gemini style)
Aliases without the version prefix (e.g. /p/{label}/{scenario}/chat/completions) are also served,
because some clients append only the endpoint name to a configured base URL.

Every request is appended to logs/mock_requests.jsonl (override with env MOCK_LOG_PATH). That file is
ground truth for "which model was actually called". Each line has: label, scenario_id, request_id,
ts, plus style, path, status, stream, requested_model, refused, answered.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from contracts.schemas import now_iso
from mock_provider import formats as F

REQ_RE = re.compile(r"REQ:([0-9a-fA-F-]{8,36})")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = ROOT / "logs" / "mock_requests.jsonl"
_LOCK = threading.Lock()

app = FastAPI(title="refusal-failover-bench mock provider", version="1.0")


def log_path() -> Path:
    return Path(os.environ.get("MOCK_LOG_PATH") or DEFAULT_LOG_PATH)


def extract_request_id(style: str, body: dict, raw: str) -> tuple[str | None, str]:
    """REQ id from the last real user message; fall back to the last REQ anywhere in the body."""
    text = F.last_user_text(style, body)
    if text:
        found = REQ_RE.findall(text)
        if found:
            return found[-1], "last_user_message"
    found = REQ_RE.findall(raw)
    if found:
        return found[-1], "body_fallback"
    return None, "missing"


def append_log(entry: dict) -> None:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with _LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


async def handle(request: Request, style: str, label: str, scenario: str, model: str | None = None,
                 force_stream: bool = False) -> JSONResponse:
    raw_bytes = await request.body()
    raw = raw_bytes.decode("utf-8", errors="replace")
    try:
        body = json.loads(raw) if raw.strip() else {}
        if not isinstance(body, dict):
            body = {}
    except json.JSONDecodeError:
        body = {}
    request_id, rid_source = extract_request_id(style, body, raw)
    stream = force_stream or bool(body.get("stream"))

    if stream:
        status, resp = 400, F.error_body(style, 400, "mock_streaming_not_supported",
                                         "The mock provider serves non-streaming responses only.")
    else:
        status, resp = F.build_response(scenario, style, label, body)

    refused = F.refusal_detector(style)(status, resp)
    append_log({
        "label": label,
        "scenario_id": scenario,
        "request_id": request_id,
        "ts": now_iso(),
        "style": style,
        "path": request.url.path,
        "status": status,
        "stream": stream,
        "requested_model": model or body.get("model"),
        "refused": refused,
        "answered": status == 200 and not refused and scenario in F.ANSWER_SCENARIOS,
        "tool_result_in_request": F.has_tool_result_after_last_user(style, body),
        "request_id_source": rid_source,
    })
    return JSONResponse(resp, status_code=status)


# --- OpenAI style -----------------------------------------------------------------------------
@app.post("/p/{label}/{scenario}/v1/chat/completions")
@app.post("/p/{label}/{scenario}/chat/completions")
async def openai_chat(label: str, scenario: str, request: Request) -> JSONResponse:
    return await handle(request, F.OPENAI, label, scenario)


# Azure OpenAI deployments path (api_base + /openai/deployments/{dep}/chat/completions)
@app.post("/p/{label}/{scenario}/openai/deployments/{deployment}/chat/completions")
async def azure_chat(label: str, scenario: str, deployment: str, request: Request) -> JSONResponse:
    return await handle(request, F.OPENAI, label, scenario, model=deployment)


# --- Anthropic style --------------------------------------------------------------------------
@app.post("/p/{label}/{scenario}/v1/messages")
@app.post("/p/{label}/{scenario}/messages")
async def anthropic_messages(label: str, scenario: str, request: Request) -> JSONResponse:
    return await handle(request, F.ANTHROPIC, label, scenario)


# --- Gemini style -----------------------------------------------------------------------------
async def _gemini(label: str, scenario: str, model_action: str, request: Request) -> JSONResponse:
    model, _, action = model_action.partition(":")
    if action == "streamGenerateContent":
        return await handle(request, F.GEMINI, label, scenario, model=model, force_stream=True)
    if action != "generateContent":
        return JSONResponse(F.error_body(F.GEMINI, 404, "NOT_FOUND", f"Unsupported Gemini action: {action!r}"), status_code=404)
    return await handle(request, F.GEMINI, label, scenario, model=model)


@app.post("/p/{label}/{scenario}/v1beta/models/{model_action}")
async def gemini_v1beta(label: str, scenario: str, model_action: str, request: Request) -> JSONResponse:
    return await _gemini(label, scenario, model_action, request)


@app.post("/p/{label}/{scenario}/v1/models/{model_action}")
async def gemini_v1(label: str, scenario: str, model_action: str, request: Request) -> JSONResponse:
    return await _gemini(label, scenario, model_action, request)


@app.post("/p/{label}/{scenario}/models/{model_action}")
async def gemini_bare(label: str, scenario: str, model_action: str, request: Request) -> JSONResponse:
    return await _gemini(label, scenario, model_action, request)


# --- Discovery / health (not logged: no model call happens) ------------------------------------
@app.get("/p/{label}/{scenario}/v1/models")
async def list_models(label: str, scenario: str) -> dict:
    return {"object": "list", "data": [{"id": label, "object": "model", "owned_by": "mock"}]}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "scenarios": sorted(F.NATIVE_STYLES), "styles": list(F.STYLES),
            "log_path": str(log_path())}
