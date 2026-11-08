"""Deterministic in-process router for building against before real adapters exist. No network."""
from contracts.schemas import RouterResult
from routers.base import RouterAdapter


class StubAdapter(RouterAdapter):
    name = "stub"
    version = "0.0.0"

    def start(self, config_name, mock_url="http://localhost:8900"):
        pass

    def supports(self, config_name) -> bool:
        return True

    def send(self, prompt, request_id, api_style="openai") -> RouterResult:
        if "REFUSE" in prompt:
            return RouterResult(final_text=None, http_status=200, reported_model="mock-a", error="refusal: content_filter")
        if "REROUTE" in prompt:
            return RouterResult(final_text="OK ANSWERED_BY=mock-b", http_status=200, reported_model="mock-b")
        return RouterResult(final_text="OK ANSWERED_BY=mock-a", http_status=200, reported_model="mock-a")
