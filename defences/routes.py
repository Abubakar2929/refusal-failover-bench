"""Routing layer for Experiment D: what each defence is allowed to call, plus the simulated
"unguarded fallback model that complies".

Routes (one object handed to every defence as its `adapter`)
    send(...)              the deployment as configured, router fallback ON (Portkey guardrail_fallback /
                           content_policy_fallback). d0 and d3 use this.
    send_no_fallback(...)  the same deployment with router fallback OFF (Portkey guardrail_control /
                           default) - PLAN.md d1 "call the router with fallback disabled".
    send_fallback(...)     an explicit call to the configured fallback model only (d1 on outage, d2 after
                           a provider refusal). `fallback_label` is the model that route reaches.

CompliantFallback (wraps any adapter)
    Simulates an unguarded fallback model that complies with record requests. When the response came
    from a fallback model (the provider's own `model` field is mock-b or mock-z) and the prompt names a
    record, the fallback's "OK ..." text is replaced by the record as returned by the data tool. The
    data tool releases every record unless a requester-bound policy is active (d3), in which case it
    verifies the HMAC token and the permissions table. mock_provider/ and routers/ are not modified.

Data tool
    fetch_record(record_id): the only way the simulated fallback reads data/canary.db.
"""
from __future__ import annotations

import contextvars
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from contracts.schemas import APPROVED_FALLBACK, OFFLIST, PRIMARY, RouterResult

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "canary.db"
RECORD_RE = re.compile(r"\bcust-\d{4}\b")
FALLBACK_LABELS = {APPROVED_FALLBACK, OFFLIST}
DENIED_TEXT = "I can't provide record {rid}: the data service denied access for this requester."


# ---------------------------------------------------------------------------------------------
# Data tool with an optional requester-bound policy (set only by d3)
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class DataPolicy:
    role: str          # role proven by a verified HMAC token (never the role claimed in the prompt)


_POLICY: contextvars.ContextVar[DataPolicy | None] = contextvars.ContextVar("data_policy", default=None)


@contextmanager
def requester_bound(policy: DataPolicy):
    token = _POLICY.set(policy)
    try:
        yield
    finally:
        _POLICY.reset(token)


def role_may_read(role: str, record_id: str, db_path: Path = DB_PATH) -> bool:
    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute("SELECT allowed FROM permissions WHERE role=? AND record_id=?", (role, record_id)).fetchone()
    finally:
        con.close()
    return bool(row and row[0])


def fetch_record(record_id: str, db_path: Path = DB_PATH) -> tuple[bool, str | None]:
    """Return (released, body). Under a requester-bound policy the role must be allowed the record."""
    policy = _POLICY.get()
    if policy is not None and not role_may_read(policy.role, record_id, db_path):
        return False, None
    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute("SELECT body FROM records WHERE id=?", (record_id,)).fetchone()
    finally:
        con.close()
    return (row is not None), (row[0] if row else None)


# ---------------------------------------------------------------------------------------------
# Compliant (leaking) fallback model
# ---------------------------------------------------------------------------------------------
class CompliantFallback:
    """Adapter wrapper: a fallback model that answers record requests with the record's contents."""

    def __init__(self, inner, db_path: Path = DB_PATH):
        self.inner = inner
        self.db_path = db_path
        self.name = getattr(inner, "name", "unknown")
        self.version = getattr(inner, "version", "unknown")

    def send(self, prompt: str, request_id: str, api_style: str = "openai") -> RouterResult:
        result = self.inner.send(prompt, request_id, api_style)
        if result.http_status != 200 or result.reported_model not in FALLBACK_LABELS:
            return result
        record_ids = list(dict.fromkeys(RECORD_RE.findall(prompt)))
        if not record_ids:
            return result
        parts = []
        for rid in record_ids:
            released, body = fetch_record(rid, self.db_path)
            parts.append(f"Here is record {rid}: {body}" if released and body else DENIED_TEXT.format(rid=rid))
        return result.model_copy(update={"final_text": " ".join(parts)})


# ---------------------------------------------------------------------------------------------
# Route set
# ---------------------------------------------------------------------------------------------
class Routes:
    def __init__(self, routed, no_fallback=None, fallback=None, fallback_label: str = APPROVED_FALLBACK):
        self.routed = routed
        self.no_fallback = no_fallback
        self.fallback = fallback
        self.fallback_label = fallback_label
        self.name = getattr(routed, "name", "unknown")
        self.version = getattr(routed, "version", "unknown")

    def send(self, prompt: str, request_id: str, api_style: str = "openai") -> RouterResult:
        return self.routed.send(prompt, request_id, api_style)

    def send_no_fallback(self, prompt: str, request_id: str, api_style: str = "openai") -> RouterResult:
        return (self.no_fallback or self.routed).send(prompt, request_id, api_style)

    def send_fallback(self, prompt: str, request_id: str, api_style: str = "openai") -> RouterResult:
        if self.fallback is None:
            return RouterResult(http_status=0, error="no explicit fallback route configured")
        return self.fallback.send(prompt, request_id, api_style)


def portkey_routes(main: bool, mock_url: str, gateway_url: str | None = None) -> Routes:
    """Routes over the real Portkey gateway (routers/portkey_adapter.py, reused, not copied).

    main=True : record prompts. routed = guardrail_fallback, no_fallback = guardrail_control (both: primary
                mock-a serving `ok` carries the deployer guardrail; mock-b does not).
    main=False: false-positive prompts. Primary mock-a serves `http400_policy` (a provider refusal of a
                benign prompt); routed = content_policy_fallback (on_status_codes [400]), no_fallback = default.
    The explicit fallback route targets mock-b serving `ok` with no guardrail.
    """
    import types

    import httpx

    import routers.portkey_adapter as pk
    from routers.portkey_adapter import GATEWAY_URL, PortkeyAdapter

    # Performance only: the adapter calls module-level httpx.post/get, which opens a new loopback connection
    # per request (~0.5 s each on Windows). Give that module a pooled client with the same post/get
    # interface; URLs, headers, bodies and per-call timeouts are unchanged. routers/ is not edited.
    if not isinstance(pk.httpx, types.SimpleNamespace):
        client = httpx.Client()
        pk.httpx = types.SimpleNamespace(post=client.post, get=client.get, HTTPError=httpx.HTTPError)

    class DirectFallback(PortkeyAdapter):
        """Single-target Portkey config that reaches only the fallback model (no guardrail)."""

        def _config(self, style: str = "openai") -> dict:
            return self._target(self.fallback_label, "ok", style)

    url = gateway_url or GATEWAY_URL
    scenario = "ok" if main else "http400_policy"
    routed_cfg, nofb_cfg = ("guardrail_fallback", "guardrail_control") if main else ("content_policy_fallback", "default")
    adapters = []
    for cfg in (routed_cfg, nofb_cfg):
        a = PortkeyAdapter(gateway_url=url)
        a.start(cfg, mock_url)
        a.set_scenario(scenario)
        adapters.append(a)
    direct = DirectFallback(gateway_url=url)
    direct.start("default", mock_url)
    return Routes(CompliantFallback(adapters[0]), CompliantFallback(adapters[1]), CompliantFallback(direct),
                  fallback_label=direct.fallback_label)


__all__ = ["CompliantFallback", "DataPolicy", "Routes", "fetch_record", "portkey_routes", "requester_bound",
           "role_may_read", "PRIMARY"]
