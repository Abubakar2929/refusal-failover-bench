"""d0 — No defence (pass-through baseline).

Sends the prompt directly through the adapter with no filtering.
"""
from __future__ import annotations

from contracts.schemas import RouterResult
from defences.base import Defence


class D0None(Defence):
    """Pass-through: the router handles everything; no defence layer."""
    name = "d0"

    def call(self, adapter, prompt: str, request_id: str,
             requester_token: str | None = None) -> RouterResult:
        return adapter.send(prompt, request_id)

