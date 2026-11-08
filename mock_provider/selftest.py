"""mock_provider selftest. Runs in-process (httpx ASGITransport): no network, no keys, < 30 s.

Checks
1. formats.py bodies are identical to contracts/refusal_formats.md (no drift from the contract).
2. Every scenario id in contracts/scenarios.json is served, on every style it is native to, with the
   exact status code and the exact JSON keys of the contract body.
3. Non-native style -> 404 scenario_not_native_to_style; streaming -> 400 mock_streaming_not_supported.
4. Non-refused answers contain ANSWERED_BY={label}; refusals do not.
5. ok_toolcall: tool call first, final text once a tool result is in the conversation (all 3 styles).
6. Every request is logged to the mock log with label, scenario_id, request_id (from the LAST user
   message), ts.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from mock_provider import formats as F  # noqa: E402

CONTRACT_MD = ROOT / "contracts" / "refusal_formats.md"
SCENARIOS = ROOT / "contracts" / "scenarios.json"


def keyset(obj, prefix=""):
    """All key paths in a JSON object (list indices collapsed to [])."""
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else k
            out.add(p)
            out |= keyset(v, p)
    elif isinstance(obj, list):
        for v in obj:
            out |= keyset(v, prefix + "[]")
    return out


def path_for(style, label, scenario):
    if style == F.OPENAI:
        return f"/p/{label}/{scenario}/v1/chat/completions"
    if style == F.ANTHROPIC:
        return f"/p/{label}/{scenario}/v1/messages"
    return f"/p/{label}/{scenario}/v1beta/models/{label}:generateContent"


def user_body(style, text, extra=None):
    if style == F.GEMINI:
        body = {"contents": [{"role": "user", "parts": [{"text": text}]}]}
    elif style == F.ANTHROPIC:
        body = {"model": "x", "max_tokens": 32, "messages": [{"role": "user", "content": text}]}
    else:
        body = {"model": "x", "messages": [{"role": "system", "content": "sys REQ:00000000-dead-beef-0000-000000000000"},
                                           {"role": "user", "content": text}]}
    if extra:
        body.update(extra)
    return body


def tool_followup_body(style, rid):
    text = f"write it REQ:{rid}"
    if style == F.OPENAI:
        return {"model": "x", "messages": [
            {"role": "user", "content": text},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "write_record", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "call_1", "content": "written"}]}
    if style == F.ANTHROPIC:
        return {"model": "x", "max_tokens": 32, "messages": [
            {"role": "user", "content": [{"type": "text", "text": text}]},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "write_record", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "written"}]}]}
    return {"contents": [
        {"role": "user", "parts": [{"text": text}]},
        {"role": "model", "parts": [{"functionCall": {"name": "write_record", "args": {}}}]},
        {"role": "user", "parts": [{"functionResponse": {"name": "write_record", "response": {"ok": True}}}]}]}


def check_contract_drift():
    md = F.contract_bodies_from_markdown(CONTRACT_MD.read_text(encoding="utf-8"))
    for sid, body in F.REFUSAL_BODIES.items():
        assert md[sid] == body, f"formats.py body for {sid} differs from contracts/refusal_formats.md"
    assert md["ok (OpenAI style)"] == F.OK_BODIES[F.OPENAI]
    assert md["ok (Anthropic style)"] == F.OK_BODIES[F.ANTHROPIC]
    assert md["ok (Gemini style)"] == F.OK_BODIES[F.GEMINI]
    assert md["ok_toolcall"] == F.OK_TOOLCALL_OPENAI
    return len(md)


def expected_contract_body(scenario, style, label):
    """The contract body the response must match key-for-key (None = no contract body for this combo)."""
    if scenario in F.REFUSAL_BODIES and (scenario != "text_refusal" or style == F.OPENAI):
        return F._subst(F.REFUSAL_BODIES[scenario], label)
    if scenario == "ok":
        return F._subst(F.OK_BODIES[style], label)
    if scenario == "ok_toolcall" and style == F.OPENAI:
        return F._subst(F.OK_TOOLCALL_OPENAI, label)
    return None


async def run_checks(log_file: Path):
    from mock_provider.app import app
    scenario_ids = [s["id"] for s in json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]]
    assert set(scenario_ids) == set(F.NATIVE_STYLES), "formats.NATIVE_STYLES must cover exactly scenarios.json"
    http_of = {s["id"]: s["http"] for s in json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]}

    transport = httpx.ASGITransport(app=app)
    sent = []  # (label, scenario, request_id)
    n = 0
    async with httpx.AsyncClient(transport=transport, base_url="http://mock", timeout=10) as client:
        for scenario in scenario_ids:
            for style in F.STYLES:
                label = F.LABELS[n % 3]
                n += 1
                rid = str(uuid.uuid4())
                r = await client.post(path_for(style, label, scenario), json=user_body(style, f"hello REQ:{rid}"))
                sent.append((label, scenario, rid))
                body = r.json()
                if style not in F.NATIVE_STYLES[scenario]:
                    assert r.status_code == 404, (scenario, style, r.status_code)
                    assert "scenario_not_native_to_style" in json.dumps(body)
                    continue
                assert r.status_code == http_of[scenario], (scenario, style, r.status_code, body)
                exp = expected_contract_body(scenario, style, label)
                if exp is not None:
                    missing = keyset(exp) - keyset(body)
                    assert not missing, f"{scenario}/{style}: missing contract keys {missing}"
                    extra = {k for k in keyset(body) - keyset(exp) if k.split(".")[0] not in F.REALISM_KEYS}
                    assert not extra, f"{scenario}/{style}: unexpected keys {extra}"
                    # values must match the contract exactly (realism-only keys aside)
                    trimmed = {k: v for k, v in body.items() if not (k in F.REALISM_KEYS and k not in exp)}
                    assert trimmed == exp, f"{scenario}/{style}: body differs from contract"
                if style == F.GEMINI and r.status_code == 200:
                    assert body.get("modelVersion") == label and "usageMetadata" in body, (scenario, body)
                text = json.dumps(body)
                refused = F.refusal_detector(style)(r.status_code, body)
                if scenario in F.ANSWER_SCENARIOS:
                    assert f"ANSWERED_BY={label}" in text, (scenario, style)
                    assert not refused, (scenario, style)
                else:
                    assert "ANSWERED_BY" not in text, (scenario, style)
                    assert refused == (scenario != "http500"), (scenario, style, refused)

        # ok_toolcall: first turn tool call, follow-up with tool result -> final text
        for style in F.STYLES:
            rid = str(uuid.uuid4())
            r1 = await client.post(path_for(style, "mock-b", "ok_toolcall"), json=user_body(style, f"go REQ:{rid}"))
            t1 = json.dumps(r1.json())
            assert "write_record" in t1 and "cust-0001" in t1, (style, t1)
            r2 = await client.post(path_for(style, "mock-b", "ok_toolcall"), json=tool_followup_body(style, rid))
            b2 = r2.json()
            assert r2.status_code == 200 and "write_record" not in json.dumps(b2) and "ANSWERED_BY=mock-b" in json.dumps(b2), (style, b2)
            sent += [("mock-b", "ok_toolcall", rid)] * 2

        # streaming refused explicitly
        rid = str(uuid.uuid4())
        r = await client.post(path_for(F.OPENAI, "mock-a", "ok"), json=user_body(F.OPENAI, f"x REQ:{rid}", {"stream": True}))
        assert r.status_code == 400 and r.json()["error"]["code"] == "mock_streaming_not_supported"
        r = await client.post(f"/p/mock-a/ok/v1beta/models/mock-a:streamGenerateContent", json=user_body(F.GEMINI, f"x REQ:{rid}"))
        assert r.status_code == 400
        sent += [("mock-a", "ok", rid)] * 2

        # unknown scenario
        r = await client.post(path_for(F.OPENAI, "mock-a", "nope"), json=user_body(F.OPENAI, "x REQ:12345678"))
        assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_scenario"
        sent.append(("mock-a", "nope", "12345678"))

        # bare alias path used by some clients
        r = await client.post("/p/mock-a/ok/chat/completions", json=user_body(F.OPENAI, "x REQ:abcdef12"))
        assert r.status_code == 200 and "ANSWERED_BY=mock-a" in r.text
        sent.append(("mock-a", "ok", "abcdef12"))

    logged = [json.loads(l) for l in log_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(logged) == len(sent), (len(logged), len(sent))
    for entry, (label, scenario, rid) in zip(logged, sent):
        for key in ("label", "scenario_id", "request_id", "ts"):
            assert key in entry, key
        assert (entry["label"], entry["scenario_id"], entry["request_id"]) == (label, scenario, rid), (entry, label, scenario, rid)
    native = sum(len(v) for v in F.NATIVE_STYLES.values())
    return len(scenario_ids), native, len(logged)


def main():
    n_md = check_contract_drift()
    with tempfile.TemporaryDirectory() as tmp:
        log_file = Path(tmp) / "mock_requests.jsonl"
        os.environ["MOCK_LOG_PATH"] = str(log_file)
        n_scen, native, n_logged = asyncio.run(run_checks(log_file))
    print(f"mock_provider OK ({n_scen} scenarios, {native} scenario x style combos served, "
          f"{n_md} contract bodies match formats.py, {n_logged} requests logged with correct label/scenario/REQ id)")


if __name__ == "__main__":
    main()
