"""Run: uvicorn contracts.fixtures.stub_provider:app --port 8900"""
import json
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from contracts.schemas import now_iso

REQ_RE = re.compile(r"REQ:([0-9a-fA-F-]{8,36})")
LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "mock_requests.jsonl"

HTTP500_BODY = {"error": {"message": "Internal server error.", "type": "server_error", "param": None, "code": "internal_error"}}
HTTP400_POLICY_BODY = {"error": {"code": "content_policy_violation", "message": "Your request was rejected as a result of our safety system.", "param": None, "type": "invalid_request_error"}}

app = FastAPI()


def log_request(label: str, scenario: str, body: bytes) -> None:
    match = REQ_RE.search(body.decode("utf-8", errors="replace"))
    entry = {"label": label, "scenario_id": scenario, "request_id": match.group(1) if match else None, "ts": now_iso()}
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def openai_ok(label: str) -> dict:
    return {"id": "chatcmpl-mock", "object": "chat.completion", "model": label,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": f"OK ANSWERED_BY={label}", "refusal": None}, "finish_reason": "stop"}]}


def anthropic_ok(label: str) -> dict:
    return {"id": "msg_mock", "type": "message", "role": "assistant", "model": label,
            "content": [{"type": "text", "text": f"OK ANSWERED_BY={label}"}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 12, "output_tokens": 6}}


def respond(label: str, scenario: str, ok_body) -> JSONResponse:
    if scenario == "ok":
        return JSONResponse(ok_body(label))
    if scenario == "http500":
        return JSONResponse(HTTP500_BODY, status_code=500)
    if scenario == "http400_policy":
        return JSONResponse(HTTP400_POLICY_BODY, status_code=400)
    return JSONResponse({"error": {"message": f"Scenario not supported by the stub: {scenario}", "type": "not_found", "param": None, "code": "unknown_scenario"}}, status_code=404)


@app.post("/p/{label}/{scenario}/v1/chat/completions")
async def chat_completions(label: str, scenario: str, request: Request) -> JSONResponse:
    log_request(label, scenario, await request.body())
    return respond(label, scenario, openai_ok)


@app.post("/p/{label}/{scenario}/v1/messages")
async def messages(label: str, scenario: str, request: Request) -> JSONResponse:
    log_request(label, scenario, await request.body())
    return respond(label, scenario, anthropic_ok)
