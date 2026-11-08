"""routers selftest. Rule: must run in under 30 seconds, with no network and no keys."""
import json
import tempfile
from pathlib import Path

from contracts.fixtures.stub_adapter import StubAdapter
from contracts.schemas import RouterResult, read_logs
from routers import common, guardrail_policy, runner

SCENARIO_HITS = {"ok": ["mock-a"], "http500": ["mock-a", "mock-b"]}


class FakeRouter(StubAdapter):
    """StubAdapter that also writes the mock's ground-truth log. http500 acts as a re-route."""

    def set_scenario(self, scenario_id):
        self.scenario = scenario_id

    def supports_cell(self, config_name, scenario):
        return self.supports(config_name)

    def send(self, prompt, request_id, api_style="openai"):
        with open(runner.LOGS_DIR / "mock_requests.jsonl", "a", encoding="utf-8") as f:
            for label in SCENARIO_HITS[self.scenario]:
                f.write(json.dumps({"label": label, "scenario_id": self.scenario, "request_id": request_id}) + "\n")
        return super().send(prompt + (" REROUTE" if self.scenario == "http500" else ""), request_id, api_style)


class UnsupportedRouter(FakeRouter):
    def supports(self, config_name):
        return False


def check_common() -> None:
    kept = common.safe_headers({"Authorization": "x", "api-key": "x", "Cookie": "x", "X-LiteLLM-Model-Id": "m",
                                "x-litellm-key-spend": "x", "x-portkey-api-key": "x", "x-request-id": "r"})
    assert kept == {"x-litellm-model-id": "m", "x-request-id": "r"}, kept
    assert common.api_base("http://m:1/", "mock-a", "ok", "openai") == "http://m:1/p/mock-a/ok/v1"
    assert common.api_base("http://m:1", "mock-b", "ok", "anthropic") == "http://m:1/p/mock-b/ok"
    assert common.make_prompt("abc") == "Reply with the word OK. REQ:abc"
    assert len(common.short_error(ValueError("x" * 999))) == common.MAX_ERROR_CHARS


def check_runner() -> None:
    runner.ADAPTERS.clear()
    runner.ADAPTERS.update(fake=FakeRouter, nope=UnsupportedRouter)
    for args in ({"router": "bad"}, {"config": "bad"}, {"scenario": "bad"}):
        try:
            runner.main("t", **args)
        except SystemExit as exc:
            assert "bad" in str(exc), exc
        else:
            raise AssertionError(f"accepted invalid name: {args}")

    runner.main("t", router="fake", config="default", scenario="ok")
    runner.main("t", router="fake", config="default", scenario="http500")
    runner.main("t", router="nope", config="default", scenario="ok")
    runner.main("t", router="fake", config="default", scenario="an200_refusal")  # filtered: must not log
    lines = read_logs(str(runner.LOGS_DIR / "exp_A.jsonl"))
    assert len(lines) == 3, len(lines)
    normal, moved, unsupported = lines

    assert (normal.rerouted, normal.answering_model, normal.disclosed_in_response) == (False, "mock-a", None)
    assert normal.refusal_kind == "none" and normal.within_allowlist is True
    assert (moved.rerouted, moved.answering_model, moved.disclosed_in_response) == (True, "mock-b", True)
    assert unsupported.not_supported is True and unsupported.rerouted is None and unsupported.answering_model is None


def check_guardrail_policy() -> None:
    assert guardrail_policy.is_blocked(guardrail_policy.blocked_prompt("abc"))
    assert not guardrail_policy.is_blocked(common.make_prompt("abc"))
    assert not guardrail_policy.is_blocked("record xcust-0001 and cust-12345")


def check_guardrail_ground_truth() -> None:
    with open(runner.LOGS_DIR / "mock_requests.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"label": "mock-b", "scenario_id": "ok", "request_id": "moved"}) + "\n")

    block = RouterResult(http_status=runner.GUARDRAIL_STATUS, error="hooks_failed")
    held, failure = runner.cell_fields(block, runner.labels_hit("held"), "blocked")
    assert failure is None and held["blocked"] is True and held["rerouted"] is False, held

    answer = RouterResult(final_text="OK ANSWERED_BY=mock-b", http_status=200, reported_model="mock-b")
    moved, failure = runner.cell_fields(answer, runner.labels_hit("moved"), "blocked")
    assert failure is None and moved["blocked"] is False, moved
    assert (moved["rerouted"], moved["answering_model"], moved["disclosed_in_response"]) == (True, "mock-b", True)

    _, failure = runner.cell_fields(RouterResult(http_status=0, error="down"), [], "blocked")
    assert failure == "down", failure


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        runner.LOGS_DIR = Path(tmp)
        check_common()
        check_runner()
        check_guardrail_policy()
        check_guardrail_ground_truth()
    print("routers selftest OK")
