"""Portkey OSS gateway adapter. The gateway must already be running; this never spawns npx."""
import json
import os

import httpx

from contracts.schemas import PRIMARY, RouterResult
from routers.common import MOCK_KEY, TIMEOUT_S, TableAdapter, api_base, safe_headers, short_error

GATEWAY_URL = os.environ.get("PORTKEY_URL", "http://127.0.0.1:8787")
HEALTH_TIMEOUT_S = 2


class PortkeyAdapter(TableAdapter):
    name = "portkey"
    version = "1.15.2"  # Keep in step with the npx pin in routers/VERSIONS.md.
    # UNVERIFIED: refusal_failover has no confirmed Portkey setting. guardrail_fallback comes in Phase 2.
    # outage_fallback_wildcard: LiteLLM-only setting.
    specs = {
        "default": None,
        "outage_fallback": {"mode": "fallback"},
        "content_policy_fallback": {"mode": "fallback", "on_status_codes": [400]},
        "offlist_fallback": {"mode": "fallback"},
    }

    def __init__(self, gateway_url: str = GATEWAY_URL, timeout: float = TIMEOUT_S) -> None:
        self.gateway_url = gateway_url
        self.timeout = timeout

    def start(self, config_name: str, mock_url: str = "http://127.0.0.1:8900") -> None:
        super().start(config_name, mock_url)
        try:
            httpx.get(self.gateway_url, timeout=HEALTH_TIMEOUT_S).raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Portkey gateway not running at {self.gateway_url}; "
                               "start it with npx @portkey-ai/gateway") from exc

    def _target(self, label: str, scenario: str) -> dict:
        return {"provider": "openai", "api_key": MOCK_KEY, "custom_host": api_base(self.mock_url, label, scenario),
                "override_params": {"model": label}}

    def _config(self) -> dict:
        primary = self._target(PRIMARY, self.scenario)
        if self.spec is None:
            return primary  # The gateway rejects "targets" without a "strategy" ("Invalid config passed").
        return {"strategy": self.spec, "targets": [primary, self._target(self.fallback_label, "ok")]}

    def send(self, prompt: str, request_id: str, api_style: str = "openai") -> RouterResult:
        if api_style != "openai":
            return RouterResult(http_status=0, error=f"api_style {api_style} not implemented for portkey")
        try:
            r = httpx.post(f"{self.gateway_url}/v1/chat/completions", timeout=self.timeout,
                           headers={"x-portkey-config": json.dumps(self._config())},
                           json={"model": PRIMARY, "messages": [{"role": "user", "content": prompt}]})
        except httpx.HTTPError as exc:
            return RouterResult(http_status=0, error=short_error(exc))
        headers = safe_headers(dict(r.headers))
        if not r.is_success:
            return RouterResult(http_status=r.status_code, headers=headers, error=r.text[:200])
        body = r.json()
        return RouterResult(final_text=body["choices"][0]["message"]["content"], http_status=r.status_code,
                            headers=headers, reported_model=body.get("model"))
