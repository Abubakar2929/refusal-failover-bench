"""LiteLLM in-process Router adapter. A fresh Router per send keeps cells independent."""
import os

from contracts.schemas import PRIMARY, RouterResult
from routers.common import MOCK_KEY, TIMEOUT_S, TableAdapter, api_base, package_version, safe_headers, short_error

TO_FALLBACK = [{"primary": ["fallback"]}]
STYLE_PREFIX = {"openai": "openai", "anthropic": "anthropic"}


def _load_litellm():
    """Import litellm without its import-time fetch of the remote cost map or telemetry."""
    # litellm/litellm_core_utils/get_model_cost_map.py: this env var forces the bundled copy.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import litellm
    litellm.telemetry = False
    return litellm


class LiteLLMAdapter(TableAdapter):
    name = "litellm"
    version = package_version("litellm")
    # UNVERIFIED: refusal_failover has no confirmed LiteLLM setting. guardrail_fallback comes in Phase 2.
    specs = {
        "default": {},
        "outage_fallback": {"fallbacks": TO_FALLBACK},
        "outage_fallback_wildcard": {"fallbacks": [{"*": ["fallback"]}]},
        "content_policy_fallback": {"content_policy_fallbacks": TO_FALLBACK},
        "offlist_fallback": {"fallbacks": TO_FALLBACK},
    }

    def _deployment(self, group: str, label: str, scenario: str, style: str) -> dict:
        return {"model_name": group, "litellm_params": {
            "model": f"{STYLE_PREFIX[style]}/{label}", "api_key": MOCK_KEY,
            "api_base": api_base(self.mock_url, label, scenario, style)}}

    def _router(self, litellm, style: str):
        deployments = [self._deployment("primary", PRIMARY, self.scenario, style),
                       self._deployment("fallback", self.fallback_label, "ok", style)]
        return litellm.Router(model_list=deployments, num_retries=0, timeout=TIMEOUT_S,
                              allowed_fails=1000, disable_cooldowns=True, **self.spec)

    def send(self, prompt: str, request_id: str, api_style: str = "openai") -> RouterResult:
        litellm = _load_litellm()
        try:
            response = self._router(litellm, api_style).completion(
                model="primary", messages=[{"role": "user", "content": prompt}])
        except Exception as exc:  # A failed cell is a result to record, never a crash.
            return RouterResult(http_status=getattr(exc, "status_code", None) or 0, error=short_error(exc))
        hidden = getattr(response, "_hidden_params", None) or {}
        headers = {**(hidden.get("additional_headers") or {}),
                   "x-litellm-model-id": hidden.get("model_id"),
                   "x-litellm-model-api-base": hidden.get("api_base")}
        return RouterResult(final_text=response.choices[0].message.content, http_status=200,
                            headers=safe_headers(headers), reported_model=response.model)
