"""d3 - Requester-bound permission check at the data.

Records are released only by the data tool (defences/routes.py: fetch_record), which, under d3, checks the
role proven by an HMAC requester token against the `permissions` table. What the prompt claims ("I am the
manager") is ignored. d3 does not change routing: the request goes through the deployment as configured
(router fallback ON), so it keeps false-positive recovery.

Steps: (1) parse and verify the token (missing, malformed, bad HMAC or a different request id -> 403);
(2) send the request with the requester-bound data policy active; (3) defence in depth: if the response
still contains a canary for a record the role may not read, block it.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from contracts.schemas import RouterResult
from data.build_db import make_hmac_token, verify_hmac_token
from defences.base import Defence
from defences.routes import DataPolicy, requester_bound, role_may_read

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "canary.db"
REQ_RE = re.compile(r"REQ:([0-9a-fA-F-]{8,36})")


class RequesterToken:
    def __init__(self, requester_id: str, role: str, request_id: str, token: str):
        self.requester_id, self.role, self.request_id, self.token = requester_id, role, request_id, token

    def verify(self) -> bool:
        return verify_hmac_token(self.token, self.requester_id, self.role, self.request_id)


def parse_requester_token(token_str: str | None) -> RequesterToken | None:
    """Format: requester_id|role|request_id|hmac. None if missing or malformed."""
    if not token_str:
        return None
    parts = token_str.split("|")
    return RequesterToken(*parts) if len(parts) == 4 else None


def make_token_string(requester_id: str, role: str, request_id: str) -> str:
    return f"{requester_id}|{role}|{request_id}|{make_hmac_token(requester_id, role, request_id)}"


def unauthorised_canaries(text: str, role: str, db_path: Path = DB_PATH) -> list[str]:
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute("SELECT id, canary FROM records").fetchall()
    finally:
        con.close()
    return [canary for rid, canary in rows if canary in text and not role_may_read(role, rid, db_path)]


def _deny(tag: str, error: str) -> RouterResult:
    return RouterResult(http_status=403, headers={"x-defence": tag}, error=error)


class D3RequesterBound(Defence):
    name = "d3"

    def call(self, adapter, prompt: str, request_id: str, requester_token: str | None = None) -> RouterResult:
        parsed = parse_requester_token(requester_token)
        if parsed is None:
            return _deny("d3-no-token", "Requester token missing or malformed")
        if not parsed.verify():
            return _deny("d3-invalid-token", "Requester token HMAC verification failed")
        if parsed.request_id != request_id:
            return _deny("d3-request-id-mismatch", "Token request_id does not match this request")

        with requester_bound(DataPolicy(role=parsed.role)):
            result = adapter.send(prompt, request_id)

        if result.final_text:
            leaked = unauthorised_canaries(result.final_text, parsed.role)
            if leaked:
                return RouterResult(http_status=403, reported_model=result.reported_model,
                                    headers={"x-defence": "d3-canary-leak-blocked"},
                                    error=f"Response contained {len(leaked)} unauthorised canary value(s)")
        return result.model_copy(update={"headers": {**result.headers, "x-defence": "d3-data-bound"}})
