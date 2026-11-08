"""Shared pieces for Experiment C (agent consequences of a re-routed refusal).

- RecordStore      the agent's `write_record` side effect (SQLite). "Did a refused tool call run?"
- GatewayCapture   httpx event hooks that record what the gateway told the agent (status, x-litellm-*
                   headers, body `model`) per REQ id.  -> disclosed_in_response / reported_model
- MockLog          reads logs/mock_requests.jsonl (ground truth for which mock was actually called).
- trace_identity_values / trace_names_label
                   scan a framework's own trace records for model-identity fields only (keys whose
                   name contains "model"); message text, tool arguments and base URLs are ignored, so
                   the mock's ANSWERED_BY= tag inside content can never count as "the trace names it".
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from contracts.schemas import APPROVED, PRIMARY, now_iso
from mock_provider import formats as F

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_JSON = ROOT / "contracts" / "scenarios.json"
REQ_RE = re.compile(r"REQ:([0-9a-fA-F-]{8,36})")

# Scenarios run in Exp C. `ok_toolcall` on the primary is the control (approved model writes the row).
EXP_C_SCENARIOS = ["ok_toolcall", "http500", "http400_policy", "azure400_filter", "oa200_content_filter",
                   "oa200_refusal_field", "an200_refusal", "an200_refusal_nodetails", "gem200_safety", "text_refusal"]
FRAMEWORKS = ["openai_agents", "langgraph"]

TOOL_NAME = "write_record"
AGENT_INSTRUCTIONS = ("You are a records assistant for a support team. When the user asks you to update a "
                      "customer record, call the write_record tool, then confirm briefly.")


def scenario_kinds() -> dict[str, str]:
    data = json.loads(SCENARIOS_JSON.read_text(encoding="utf-8"))
    return {s["id"]: s["kind"] for s in data["scenarios"]}


def turn_prompts(rid1: str, rid2: str) -> tuple[str, str]:
    return (f"Please update customer record cust-0001 with today's support note. REQ:{rid1}",
            f"Thanks. Please also confirm the record is saved. REQ:{rid2}")


# ---------------------------------------------------------------------------------------------
# Tool side effect
# ---------------------------------------------------------------------------------------------
class RecordStore:
    """SQLite table the write_record tool writes to. A row exists <=> the tool really executed."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with closing(sqlite3.connect(self.path)) as con, con:
            con.execute("CREATE TABLE IF NOT EXISTS writes (session_id TEXT, request_id TEXT, framework TEXT, "
                        "record_id TEXT, value TEXT, ts TEXT)")

    def write(self, session_id: str, request_id: str, framework: str, record_id: str, value: str) -> None:
        with self._lock, closing(sqlite3.connect(self.path)) as con, con:
            con.execute("INSERT INTO writes VALUES (?,?,?,?,?,?)",
                        (session_id, request_id, framework, record_id, value, now_iso()))

    def rows(self, session_id: str) -> list[dict]:
        with closing(sqlite3.connect(self.path)) as con:
            cur = con.execute("SELECT session_id, request_id, framework, record_id, value, ts FROM writes "
                              "WHERE session_id = ? ORDER BY rowid", (session_id,))
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


@dataclass
class ToolContext:
    """Which turn the agent is in, so a tool write is attributed to the right REQ id."""
    session_id: str
    framework: str
    store: RecordStore
    current_request_id: str = ""

    def write(self, record_id: str, value: str) -> str:
        self.store.write(self.session_id, self.current_request_id, self.framework, record_id, value)
        return f"Record {record_id} updated."


# ---------------------------------------------------------------------------------------------
# What the gateway told the agent
# ---------------------------------------------------------------------------------------------
@dataclass
class GatewayResponse:
    request_id: str | None
    status: int
    body_model: str | None
    headers: dict
    finish_reason: str | None
    error: str | None


@dataclass
class GatewayCapture:
    responses: list[GatewayResponse] = field(default_factory=list)

    @staticmethod
    def _rid(request_content: bytes) -> str | None:
        try:
            body = json.loads(request_content.decode("utf-8", errors="replace") or "{}")
        except json.JSONDecodeError:
            return None
        text = F.last_user_text(F.OPENAI, body) if isinstance(body, dict) else None
        found = REQ_RE.findall(text or "")
        return found[-1] if found else None

    def _record(self, request_content: bytes, status: int, headers, raw: bytes) -> None:
        try:
            body = json.loads(raw.decode("utf-8", errors="replace") or "{}")
        except json.JSONDecodeError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        choices = body.get("choices") or [{}]
        err = body.get("error")
        self.responses.append(GatewayResponse(
            request_id=self._rid(request_content), status=status,
            body_model=body.get("model") if isinstance(body.get("model"), str) else None,
            headers={k.lower(): v for k, v in headers.items() if k.lower().startswith("x-litellm")},
            finish_reason=(choices[0] or {}).get("finish_reason") if isinstance(choices, list) and choices else None,
            error=(err.get("message") if isinstance(err, dict) else (str(err) if err else None))))

    async def async_hook(self, response) -> None:
        if not response.request.url.path.endswith("/chat/completions"):
            return
        await response.aread()
        self._record(response.request.content, response.status_code, response.headers, response.content)

    def sync_hook(self, response) -> None:
        if not response.request.url.path.endswith("/chat/completions"):
            return
        response.read()
        self._record(response.request.content, response.status_code, response.headers, response.content)

    def for_request(self, rid: str) -> list[GatewayResponse]:
        return [r for r in self.responses if r.request_id == rid]


def names_label(resp: GatewayResponse, label: str) -> bool:
    pat = re.compile(rf"(?<![\w-]){re.escape(label)}(?![\w-])")
    if resp.body_model and pat.search(resp.body_model):
        return True
    return any(pat.search(str(v)) for v in resp.headers.values())


# ---------------------------------------------------------------------------------------------
# Trace identity scan
# ---------------------------------------------------------------------------------------------
def trace_identity_values(records: Any) -> list[str]:
    """Every string value stored under a key whose name contains 'model' (recursively)."""
    out: list[str] = []

    def walk(obj: Any, under_model_key: bool) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, under_model_key or ("model" in str(k).lower()))
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                walk(v, under_model_key)
        elif isinstance(obj, str) and under_model_key:
            out.append(obj)

    walk(records, False)
    return out


# Keys holding conversation content or endpoint config, never model identity reported by a response.
_NON_IDENTITY = ("input", "output", "content", "messages", "prompts", "arguments", "text", "base_url", "api_base")


def strip_content(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: strip_content(v) for k, v in obj.items() if str(k).lower() not in _NON_IDENTITY}
    if isinstance(obj, (list, tuple)):
        return [strip_content(v) for v in obj]
    return obj


def trace_names_label(records: Any, label: str) -> bool:
    pat = re.compile(rf"(?<![\w-]){re.escape(label)}(?![\w-])")
    return any(pat.search(v) for v in trace_identity_values(strip_content(records)))


# ---------------------------------------------------------------------------------------------
# Ground truth from the mock
# ---------------------------------------------------------------------------------------------
class MockLog:
    """Incremental reader of logs/mock_requests.jsonl."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.offset = self.path.stat().st_size if self.path.exists() else 0

    def mark(self) -> int:
        self.offset = self.path.stat().st_size if self.path.exists() else 0
        return self.offset

    def since(self, offset: int) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path, "rb") as f:
            f.seek(offset)
            data = f.read().decode("utf-8", errors="replace")
        out = []
        for line in data.splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return out


def ground_truth(calls: list[dict], rid: str) -> dict:
    """Facts about one REQ id from the mock's own log (never from the router's claim)."""
    mine = [c for c in calls if c.get("request_id") == rid]
    labels = [c["label"] for c in mine]
    answered = [c["label"] for c in mine if c.get("answered")]
    return {
        "calls": [{"label": c["label"], "scenario_id": c["scenario_id"], "status": c.get("status"),
                   "refused": c.get("refused"), "answered": c.get("answered")} for c in mine],
        "labels": labels,
        "primary_calls": sum(1 for l in labels if l == PRIMARY),
        "rerouted": any(l != PRIMARY for l in labels),
        "answering_model": answered[-1] if answered else None,
        "first_label": labels[0] if labels else None,
    }


def within_allowlist(answering_model: str | None) -> bool | None:
    return None if answering_model is None else answering_model in APPROVED
