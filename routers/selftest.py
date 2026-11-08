"""routers selftest. Rule: must run in under 30 seconds, with no network and no keys."""
import json
import tempfile
from pathlib import Path

from contracts.fixtures.stub_adapter import StubAdapter
from contracts.schemas import read_logs
from routers import common, runner

SCENARIO_HITS = {"ok": ["mock-a"], "http500": ["mock-a", "mock-b"]}


class FakeRouter(StubAdapter):
    """StubAdapter that also writes the mock's ground-truth log. http500 acts as a re-route."""

    def set_scenario(self, scenario_id):
        self.scenario = scenario_id

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


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        runner.LOGS_DIR = Path(tmp)
        check_common()
        check_runner()
    print("routers selftest OK")
