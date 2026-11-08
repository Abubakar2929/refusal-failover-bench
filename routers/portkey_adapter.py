"""Portkey OSS gateway adapter. The gateway must already be running; this never spawns npx."""
import json
import os

import httpx

from contracts.schemas import PRIMARY, RouterResult
from routers.common import GUARDRAIL_CONTROL, MOCK_KEY, TIMEOUT_S, TableAdapter, api_base, safe_headers, short_error
from routers.guardrail_policy import PATTERN

GATEWAY_URL = os.environ.get("PORTKEY_URL", "http://127.0.0.1:8787")
HEALTH_TIMEOUT_S = 2
# @portkey-ai/gateway 1.15.2 build/start-server.js:2 (minified): default.regexMatch at col 31062 reads rule/not, with
# verdict `not ? !matched : matched`, so not=true fails on a match; ou() at col 436438 maps these keys; deny gives 446.
GUARDRAIL = [{"default.regexMatch": {"rule": PATTERN, "not": True}, "deny": True}]
GUARDED_CONFIGS = ("guardrail_fallback", GUARDRAIL_CONTROL)
# google: @portkey-ai/gateway 1.15.2 build/start-server.js:2 (minified) col ~264800 sends /v1beta/models/{model}:generateContent.
STYLE_PROVIDER = {"openai": "openai", "anthropic": "anthropic", "gemini": "google"}


class PortkeyAdapter(TableAdapter):
    name = "portkey"
    version = "1.15.2"  # Keep in step with the npx pin in routers/VERSIONS.md.
    styles = tuple(STYLE_PROVIDER)
    # UNVERIFIED: refusal_failover has no confirmed Portkey setting.
    # outage_fallback_wildcard: LiteLLM-only setting.
    specs = {
        "default": None,
        "outage_fallback": {"mode": "fallback"},
        "content_policy_fallback": {"mode": "fallback", "on_status_codes": [400]},
        "offlist_fallback": {"mode": "fallback"},
        "guardrail_fallback": {"mode": "fallback", "on_status_codes": [446]},
        GUARDRAIL_CONTROL: None,
    }

    def __init__(self, gateway_url: str = GATEWAY_URL, timeout: float = TIMEOUT_S) -> None:
        self.gateway_url = gateway_url
        self.timeout = timeout

    def start(self, config_name: str, mock_url: str = "http://127.0.0.1:8900") -> None:
        super().start(config_name, mock_url)
        self.guarded = config_name in GUARDED_CONFIGS
        try:
            httpx.get(self.gateway_url, timeout=HEALTH_TIMEOUT_S).raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Portkey gateway not running at {self.gateway_url}; "
                               "start it with npx @portkey-ai/gateway") from exc

    def _target(self, label: str, scenario: str, style: str) -> dict:
        return {"provider": STYLE_PROVIDER[style], "api_key": MOCK_KEY,
                "custom_host": api_base(self.mock_url, label, scenario, style), "override_params": {"model": label}}

    def _config(self, style: str = "openai") -> dict:
        primary = self._target(PRIMARY, self.scenario, style)
        if self.guarded:
            primary["input_guardrails"] = GUARDRAIL
        if self.spec is None:
            return primary  # The gateway rejects "targets" without a "strategy" ("Invalid config passed").
        return {"strategy": self.spec, "targets": [primary, self._target(self.fallback_label, "ok", style)]}

    def send(self, prompt: str, request_id: str, api_style: str = "openai") -> RouterResult:
        if api_style not in self.styles:
            return RouterResult(http_status=0, error=f"api_style {api_style} not implemented for portkey")
        try:
            r = httpx.post(f"{self.gateway_url}/v1/chat/completions", timeout=self.timeout,
                           headers={"x-portkey-config": json.dumps(self._config(api_style))},
                           json={"model": PRIMARY, "messages": [{"role": "user", "content": prompt}]})
        except httpx.HTTPError as exc:
            return RouterResult(http_status=0, error=short_error(exc))
        headers = safe_headers(dict(r.headers))
        if not r.is_success:
            return RouterResult(http_status=r.status_code, headers=headers, error=r.text[:200])
        body = r.json()
        # .get: the gateway omits "content" entirely for a Gemini SAFETY block.
        return RouterResult(final_text=body["choices"][0]["message"].get("content"), http_status=r.status_code,
                            headers=headers, reported_model=body.get("model"))
