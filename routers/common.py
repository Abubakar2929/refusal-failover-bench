"""Helpers shared by every router adapter: mock URLs, prompts, header filtering, config tables."""
from importlib.metadata import PackageNotFoundError, version

from contracts.schemas import APPROVED_FALLBACK, OFFLIST
from routers.base import RouterAdapter

MOCK_KEY = "mock-not-a-secret"
TIMEOUT_S = 10
MAX_ERROR_CHARS = 200
SAFE_PREFIXES = ("x-litellm-", "x-portkey-", "x-bifrost-", "otari-", "x-request-id")
SECRET_MARKERS = ("authorization", "key", "token", "cookie")
GUARDRAIL_CONTROL = "guardrail_control"  # Runner-only: the guardrail with no fallback. Logged as config "default".
# Wire format each scenario is sent in; the mock serves a refusal only on its native style.
SCENARIO_STYLE = {
    "ok": "openai", "ok_toolcall": "openai", "http500": "openai", "http400_policy": "openai",
    "azure400_filter": "openai", "oa200_content_filter": "openai", "oa200_refusal_field": "openai",
    "text_refusal": "openai", "an200_refusal": "anthropic", "an200_refusal_nodetails": "anthropic",
    "gem200_safety": "gemini",
}


def api_base(mock_url: str, label: str, scenario: str, style: str = "openai") -> str:
    """Build the per-deployment base URL from PLAN.md 4.1; the SDKs append the endpoint path."""
    base = f"{mock_url.rstrip('/')}/p/{label}/{scenario}"
    return f"{base}/v1" if style == "openai" else base


def make_prompt(request_id: str) -> str:
    """Return the fixed prompt; the mock reads REQ:<id> from it to tie requests to cells."""
    return f"Reply with the word OK. REQ:{request_id}"


def safe_headers(headers: dict) -> dict:
    """Keep router-identity headers only, so credentials can never reach the logs."""
    lowered = {str(k).lower(): str(v) for k, v in headers.items()}
    return {k: v for k, v in lowered.items()
            if k.startswith(SAFE_PREFIXES) and not any(m in k for m in SECRET_MARKERS)}


def short_error(exc: Exception) -> str:
    """Summarise an exception without its repr, which may carry request headers."""
    return f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS]


def package_version(package: str) -> str:
    """Return the installed version, so importing an adapter never requires its router."""
    try:
        return version(package)
    except PackageNotFoundError:
        return "not-installed"


class TableAdapter(RouterAdapter):
    """Adapter driven by a `specs` table of {config name: router settings}. Absent means unsupported."""

    specs: dict = {}
    styles: tuple = ("openai",)
    scenario = "ok"

    def supports(self, config_name: str) -> bool:
        return config_name in self.specs

    def supports_cell(self, config_name: str, scenario: str) -> bool:
        """Return True if this adapter can run the config for the scenario."""
        return self.supports(config_name) and SCENARIO_STYLE[scenario] in self.styles

    def set_scenario(self, scenario_id: str) -> None:
        """Set the scenario the primary deployment serves on the next send."""
        self.scenario = scenario_id

    def start(self, config_name: str, mock_url: str = "http://127.0.0.1:8900") -> None:
        if not self.supports(config_name):
            raise ValueError(f"{self.name} does not support config {config_name!r}")
        self.spec = self.specs[config_name]
        self.mock_url = mock_url
        self.fallback_label = OFFLIST if config_name == "offlist_fallback" else APPROVED_FALLBACK
