"""LangChain adapter: ChatOpenAI with Runnable.with_fallbacks."""
from pydantic import BaseModel, ValidationError

from contracts.schemas import PRIMARY, RouterResult
from routers.common import MOCK_KEY, SCENARIO_STYLE, TIMEOUT_S, TableAdapter, api_base, package_version, short_error


class Answer(BaseModel):
    text: str


class LangChainAdapter(TableAdapter):
    name = "langchain"
    version = package_version("langchain-core")
    # UNVERIFIED: gemini needs langchain-google-genai, which is not installed and not on the PLAN.md 8.6 list.
    styles = ("openai", "anthropic")
    # content_policy_fallback: with_fallbacks has no content-policy-specific option.
    # guardrail_fallback: LangChain has no deployer guardrail in this setup.
    # outage_fallback_wildcard: LiteLLM-only setting.
    specs = {
        "default": {"fallback": False},
        "outage_fallback": {"fallback": True},
        "refusal_failover": {"fallback": True, "structured": True},
        "offlist_fallback": {"fallback": True},
    }

    def supports_cell(self, config_name: str, scenario: str) -> bool:
        """refusal_failover relies on OpenAIRefusalError, so it exists only on the OpenAI path."""
        return super().supports_cell(config_name, scenario) and (
            SCENARIO_STYLE[scenario] == "openai" or not self.specs[config_name].get("structured"))

    def _model(self, label: str, scenario: str, style: str):
        if style == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(base_url=api_base(self.mock_url, label, scenario, style), api_key=MOCK_KEY,
                                 model=label, max_retries=0, timeout=TIMEOUT_S)
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(base_url=api_base(self.mock_url, label, scenario), api_key=MOCK_KEY, model=label,
                          max_retries=0, timeout=TIMEOUT_S)

    def _chain(self, style: str):
        primary, fallback = self._model(PRIMARY, self.scenario, style), self._model(self.fallback_label, "ok", style)
        if self.spec.get("structured"):
            import openai
            from langchain_openai.chat_models.base import OpenAIRefusalError
            # Refusals and API errors only: the mock's plain-text answers fail JSON parsing, which is
            # not a provider failure. The fallback stays unstructured so its text can be read.
            return primary.with_structured_output(Answer).with_fallbacks(
                [fallback], exceptions_to_handle=(OpenAIRefusalError, openai.OpenAIError))
        return primary.with_fallbacks([fallback]) if self.spec["fallback"] else primary

    def send(self, prompt: str, request_id: str, api_style: str = "openai") -> RouterResult:
        if api_style not in self.styles:
            return RouterResult(http_status=0, error=f"api_style {api_style} not implemented for langchain")
        try:
            message = self._chain(api_style).invoke(prompt)
        except ValidationError as exc:  # The model answered in plain text; the input holds that answer.
            return RouterResult(final_text=str(exc.errors()[0]["input"]), http_status=200)
        except Exception as exc:  # A failed cell is a result to record, never a crash.
            return RouterResult(http_status=getattr(exc, "status_code", None) or 0, error=short_error(exc))
        metadata = getattr(message, "response_metadata", {})
        return RouterResult(final_text=message.text, http_status=200, reported_model=metadata.get("model_name"))
