"""agent_exp selftest. In-process only (no network, no keys), < 30 s on a warm interpreter.

Both real agent frameworks (OpenAI Agents SDK, LangGraph) talk to an in-process fake gateway (an httpx
transport) in front of the real mock provider ASGI app. The fake gateway either passes refusals
through or falls back to mock-b, like a router would. Checks that the Exp C measurement pipeline
(ground truth from the mock log, tool side effect, gateway disclosure, trace scan, session pinning,
refusal-to-caller) produces the right LogLine fields, plus LiteLLM config generation.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from agent_exp import gateway as G  # noqa: E402
from agent_exp.common import EXP_C_SCENARIOS, MockLog, RecordStore, trace_names_label  # noqa: E402
from mock_provider import formats as F  # noqa: E402


class FakeGateway(httpx.AsyncBaseTransport):
    """model 'agent-<scenario>' -> mock-a/<scenario>; on refusal or 5xx optionally retry on mock-b."""

    def __init__(self, app, fallback: bool, body_model_from_upstream: bool = True):
        self.inner = httpx.ASGITransport(app=app)
        self.fallback = fallback
        self.body_model_from_upstream = body_model_from_upstream

    async def _call(self, label, scenario, body: bytes):
        req = httpx.Request("POST", f"http://mock/p/{label}/{scenario}/v1/chat/completions", content=body,
                            headers={"content-type": "application/json"})
        resp = await self.inner.handle_async_request(req)
        raw = await resp.aread()
        return resp.status_code, json.loads(raw or b"{}")

    async def handle_async_request(self, request):
        body = await request.aread()
        model = json.loads(body)["model"]
        scenario = model.removeprefix("agent-")
        label = "mock-a"
        status, data = await self._call(label, scenario, body)
        refused = F.refusal_detector(F.OPENAI)(status, data) or status >= 500
        if refused and self.fallback:
            label = "mock-b"
            status, data = await self._call(label, "ok_toolcall", body)
        headers = {"content-type": "application/json",
                   "x-litellm-model-api-base": f"http://mock/p/{label}/{scenario if label == 'mock-a' else 'ok_toolcall'}/v1"}
        return httpx.Response(status, headers=headers, content=json.dumps(data).encode(), request=request)


async def one(framework, app, scenario, fallback, store, mock_log):
    from agent_exp.runner import evaluate, run_session
    client = httpx.AsyncClient(transport=FakeGateway(app, fallback), timeout=10)
    try:
        rid1, rid2, sid, session, calls = await run_session(framework, "http://gw/v1", "sk-test", scenario, store,
                                                            mock_log, http_client=client)
    finally:
        await client.aclose()
    outcome, audit = evaluate(session, calls, rid1, rid2, store, sid)
    return outcome, audit


def check_configs():
    try:
        import yaml
    except ImportError:  # pragma: no cover
        yaml = None
    for cfg in G.EXP_C_CONFIGS:
        c = G.build_config(cfg, "http://localhost:8900", "sk-x")
        groups = {m["model_name"] for m in c["model_list"]}
        assert {f"agent-{s}" for s in EXP_C_SCENARIOS} | {"agent-fallback", "agent-offlist"} == groups, cfg
        s = c["litellm_settings"]
        assert s["num_retries"] == 0
        if cfg == "default":
            assert "fallbacks" not in s and "content_policy_fallbacks" not in s
        if cfg == "outage_fallback_wildcard":
            assert s["fallbacks"] == [{"*": ["agent-fallback"]}]
        if cfg == "content_policy_fallback":
            assert "fallbacks" not in s and len(s["content_policy_fallbacks"]) == len(EXP_C_SCENARIOS)
        if cfg == "offlist_fallback":
            assert all(list(d.values())[0] == ["agent-offlist"] for d in s["fallbacks"] + s["content_policy_fallbacks"])
        if yaml is not None:
            assert yaml.safe_load(G.to_yaml(c)) == c, f"YAML round trip failed for {cfg}"
    prov = {s: G.deployment("mock-a", s, "http://m")["model"].split("/")[0] for s in EXP_C_SCENARIOS}
    assert prov["an200_refusal"] == "anthropic" and prov["gem200_safety"] == "gemini" and prov["azure400_filter"] == "azure"
    assert prov["oa200_content_filter"] == "openai"


def check_trace_scan():
    assert not trace_names_label([{"output": "ANSWERED_BY=mock-b", "model": "agent-x"}], "mock-b")
    assert not trace_names_label([{"model_config": {"base_url": "http://h/p/mock-b/v1"}}], "mock-b")
    assert trace_names_label([{"llm_output": {"model_name": "mock-b"}}], "mock-b")
    assert not trace_names_label([{"llm_output": {"model_name": "mock-bb"}}], "mock-b")


async def check_frameworks(tmp: Path):
    from mock_provider.app import app
    store = RecordStore(tmp / "records.sqlite")
    mock_log = MockLog(tmp / "mock_requests.jsonl")
    results = {}
    for fw in ("openai_agents", "langgraph"):
        # 1. control: primary answers with a tool call itself
        o, _ = await one(fw, app, "ok_toolcall", True, store, mock_log)
        assert o["rerouted"] is False and o["answering_model"] == "mock-a" and o["tool_call_executed"], (fw, o)
        assert o["refusal_returned_to_caller"] is False and o["session_pinned"] is None, (fw, o)
        # 2. 200-OK refusal re-routed by the gateway -> fallback's tool call runs
        o, audit = await one(fw, app, "oa200_content_filter", True, store, mock_log)
        assert o["rerouted"] is True and o["answering_model"] == "mock-b" and o["within_allowlist"] is True, (fw, o)
        assert o["tool_call_executed"] is True and o["disclosed_in_response"] is True, (fw, o)
        assert o["session_pinned"] is False, (fw, o, audit["mock_calls_turn2"])   # fake gateway always tries primary
        assert o["refusal_returned_to_caller"] is False and o["reported_model"] == "mock-b", (fw, o)
        assert any(w["value"] == "ANSWERED_BY=mock-b" for w in audit["tool_writes"]), audit["tool_writes"]
        results[fw] = o["trace_names_model"]
        # 3. same refusal with no fallback -> refusal reaches the agent, no tool call
        o, _ = await one(fw, app, "oa200_content_filter", False, store, mock_log)
        assert o["rerouted"] is False and o["tool_call_executed"] is False and o["refusal_returned_to_caller"], (fw, o)
        # 4. HTTP 400 policy with no fallback -> agent gets an error
        o, audit = await one(fw, app, "http400_policy", False, store, mock_log)
        assert o["refusal_returned_to_caller"] and audit["turns"][0]["error"], (fw, audit["turns"])
    # The Agents SDK's generation span records the requested model name only; LangChain records the
    # response body's `model`. Both behaviours are what Exp C measures; assert the pipeline sees them.
    assert results["openai_agents"] is False, results
    assert results["langgraph"] is True, results
    return results


def main():
    t0 = time.perf_counter()
    check_configs()
    check_trace_scan()
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["MOCK_LOG_PATH"] = str(Path(tmp) / "mock_requests.jsonl")
        os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "0"
        results = asyncio.run(check_frameworks(Path(tmp)))
    print(f"agent_exp OK (5 LiteLLM configs generated, trace scan ignores content, 2 frameworks x 4 sessions "
          f"through in-process fake gateway; trace names fallback: {results}; {time.perf_counter() - t0:.1f}s)")


if __name__ == "__main__":
    main()
