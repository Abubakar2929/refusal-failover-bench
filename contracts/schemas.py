"""Shared contracts. FROZEN after Phase 0. Change only after telling the team, and bump SCHEMA_VERSION. See PLAN.md section 4."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel

SCHEMA_VERSION = 1
PRIMARY = "mock-a"; APPROVED_FALLBACK = "mock-b"; OFFLIST = "mock-z"
APPROVED = {PRIMARY, APPROVED_FALLBACK}
CONFIGS = ["default", "outage_fallback", "outage_fallback_wildcard", "content_policy_fallback",
           "refusal_failover", "guardrail_fallback", "offlist_fallback"]

class RouterResult(BaseModel):
    final_text: Optional[str] = None
    http_status: int
    headers: dict = {}
    reported_model: Optional[str] = None
    error: Optional[str] = None

class LogLine(BaseModel):
    exp: Literal["A", "B", "C", "D"]
    run_id: str
    request_id: str
    rep: int = 0
    router: Optional[str] = None
    router_version: Optional[str] = None
    config: Optional[str] = None
    scenario_id: Optional[str] = None
    refusal_kind: Optional[str] = None
    rerouted: Optional[bool] = None
    answering_model: Optional[str] = None
    reported_model: Optional[str] = None
    disclosed_in_response: Optional[bool] = None
    within_allowlist: Optional[bool] = None
    refusal_returned_to_caller: Optional[bool] = None
    not_supported: Optional[bool] = None
    tool_call_executed: Optional[bool] = None
    trace_names_model: Optional[bool] = None
    session_pinned: Optional[bool] = None
    defence: Optional[str] = None
    attack: Optional[str] = None
    legit_request: Optional[bool] = None
    canary_leaked: Optional[bool] = None
    blocked: Optional[bool] = None
    recovered: Optional[bool] = None
    model_family: Optional[str] = None
    ts: str = ""

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def write_log(line: LogLine, logs_dir: str = "logs") -> None:
    os.makedirs(logs_dir, exist_ok=True)
    if not line.ts:
        line.ts = now_iso()
    with open(os.path.join(logs_dir, f"exp_{line.exp}.jsonl"), "a", encoding="utf-8") as f:
        f.write(line.model_dump_json() + "\n")

def read_logs(path: str) -> list[LogLine]:
    with open(path, encoding="utf-8") as f:
        return [LogLine(**json.loads(r)) for r in f if r.strip()]
