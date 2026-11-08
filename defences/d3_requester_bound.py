"""d3 — Requester-bound permission check.

Records are released only by a data tool that verifies the HMAC requester
token against the permissions table. Ignores what the prompt claims about
the requester's role.

This is the strongest defence: even if a prompt says "I am the manager",
the token proves the actual role.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from contracts.schemas import RouterResult
from defences.base import Defence
from data.build_db import verify_hmac_token, HMAC_SECRET

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "canary.db"

# Pattern to extract record IDs from prompts
RECORD_ID_RE = re.compile(r"(cust-\d{4})")


def _check_permission(role: str, record_id: str) -> bool:
    """Check if the given role is allowed to access the record."""
    if not DB_PATH.exists():
        return False
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT allowed FROM permissions WHERE role=? AND record_id=?",
        (role, record_id)
    ).fetchone()
    conn.close()
    if row is None:
        return False
    return bool(row[0])


def _extract_record_ids(text: str) -> list[str]:
    """Extract all record IDs (cust-XXXX) from the prompt."""
    return RECORD_ID_RE.findall(text)


def _extract_request_id(text: str) -> str | None:
    """Extract REQ:uuid from the prompt."""
    match = re.search(r"REQ:([0-9a-fA-F-]{8,36})", text)
    return match.group(1) if match else None


class RequesterToken:
    """Parsed requester token with claims."""
    def __init__(self, requester_id: str, role: str, request_id: str, token: str):
        self.requester_id = requester_id
        self.role = role
        self.request_id = request_id
        self.token = token

    def verify(self) -> bool:
        """Verify the HMAC signature."""
        return verify_hmac_token(self.token, self.requester_id, self.role, self.request_id)


def parse_requester_token(token_str: str | None) -> RequesterToken | None:
    """Parse a requester token string in format: requester_id|role|request_id|hmac.

    Returns None if the string is invalid.
    """
    if not token_str:
        return None
    parts = token_str.split("|")
    if len(parts) != 4:
        return None
    return RequesterToken(
        requester_id=parts[0],
        role=parts[1],
        request_id=parts[2],
        token=parts[3],
    )


def make_token_string(requester_id: str, role: str, request_id: str) -> str:
    """Create a complete token string: requester_id|role|request_id|hmac."""
    from data.build_db import make_hmac_token
    hmac_val = make_hmac_token(requester_id, role, request_id)
    return f"{requester_id}|{role}|{request_id}|{hmac_val}"


class D3RequesterBound(Defence):
    """Requester-bound permission check.

    Steps:
    1. Parse and verify the HMAC token (reject if invalid/missing).
    2. Extract record IDs from the prompt.
    3. Check if the token's role has permission for each record.
    4. If any record is not allowed → block.
    5. If all records allowed (or no records referenced) → pass through.
    """
    name = "d3"

    def call(self, adapter, prompt: str, request_id: str,
             requester_token: str | None = None) -> RouterResult:
        # Step 1: Parse and verify token
        parsed = parse_requester_token(requester_token)
        if parsed is None:
            return RouterResult(
                final_text=None,
                http_status=403,
                headers={"x-defence": "d3-no-token"},
                error="Requester token missing or malformed",
            )

        if not parsed.verify():
            return RouterResult(
                final_text=None,
                http_status=403,
                headers={"x-defence": "d3-invalid-token"},
                error="Requester token HMAC verification failed",
            )

        # Step 1b: Verify the token's request_id matches the call's request_id
        # This prevents token replay across different requests
        if parsed.request_id != request_id:
            return RouterResult(
                final_text=None,
                http_status=403,
                headers={"x-defence": "d3-request-id-mismatch"},
                error=f"Token request_id '{parsed.request_id}' does not match call request_id '{request_id}'",
            )

        # Step 2: Extract record IDs from the prompt
        record_ids = _extract_record_ids(prompt)

        # Step 3: Check permissions for each referenced record
        for rec_id in record_ids:
            if not _check_permission(parsed.role, rec_id):
                return RouterResult(
                    final_text=None,
                    http_status=403,
                    headers={"x-defence": "d3-permission-denied",
                             "x-denied-record": rec_id,
                             "x-token-role": parsed.role},
                    error=f"Role '{parsed.role}' does not have permission for record '{rec_id}'",
                )

        # Step 4: All checks passed — forward to adapter
        result = adapter.send(prompt, request_id)

        # Step 5: Post-check — verify response doesn't leak canaries for unauthorized records
        # (defense in depth: even if the model somehow returns unauthorized data)
        if result.final_text:
            leaked = _check_canary_leak(result.final_text, parsed.role)
            if leaked:
                return RouterResult(
                    final_text=None,
                    http_status=403,
                    headers={"x-defence": "d3-canary-leak-blocked",
                             "x-leaked-canaries": ",".join(leaked)},
                    error=f"Response contained unauthorized canary data: {', '.join(leaked)}",
                )

        return result


def _check_canary_leak(text: str, role: str) -> list[str]:
    """Check if the response text contains canary values for records the role cannot access.

    Returns list of leaked canary tags, or empty list if clean.
    """
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    # Get all canaries and their record IDs
    rows = conn.execute("SELECT id, canary FROM records").fetchall()
    leaked = []
    for rec_id, canary in rows:
        if canary in text:
            # Check if this role has permission
            perm = conn.execute(
                "SELECT allowed FROM permissions WHERE role=? AND record_id=?",
                (role, rec_id)
            ).fetchone()
            if perm is None or not perm[0]:
                leaked.append(canary)
    conn.close()
    return leaked
