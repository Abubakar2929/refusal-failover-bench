"""Live demo for the video: one 200-OK refusal re-routed by LiteLLM, shown three ways.

    python -m agent_exp.demo                                   # an200_refusal, content_policy_fallback
    python -m agent_exp.demo --scenario gem200_safety --config offlist_fallback
    python -m agent_exp.demo --config default                  # same request, no fallback: refusal stays

Prints (1) the raw gateway response and its x-litellm-* headers, (2) what the mock provider says
was actually called, and (3) the same request through a real agent (OpenAI Agents SDK): did the
refused tool call run, and does the agent's trace say which model answered?
Writes nothing to logs/exp_*.jsonl (demo only); uses a temporary mock log.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from agent_exp.common import (MockLog, RecordStore, ToolContext, ground_truth, trace_identity_values,  # noqa: E402
                              strip_content, turn_prompts)
from agent_exp.frameworks import run_openai_agents_session  # noqa: E402
from agent_exp.gateway import EXP_C_CONFIGS, LiteLLMProxy, MockServer, model_group  # noqa: E402
from agent_exp.common import EXP_C_SCENARIOS  # noqa: E402


def banner(t: str) -> None:
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="an200_refusal", choices=EXP_C_SCENARIOS)
    ap.add_argument("--config", default="content_policy_fallback", choices=EXP_C_CONFIGS)
    ap.add_argument("--mock-port", type=int, default=8911)
    ap.add_argument("--proxy-port", type=int, default=4111)
    a = ap.parse_args()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        os.environ["MOCK_LOG_PATH"] = str(tmp / "mock_requests.jsonl")
        mock_url = f"http://127.0.0.1:{a.mock_port}"
        with MockServer(mock_url, tmp), LiteLLMProxy(a.config, mock_url, a.proxy_port, tmp) as proxy:
            mock_log = MockLog(tmp / "mock_requests.jsonl")

            banner(f"1. Raw request through LiteLLM  (config={a.config}, primary mock-a serves {a.scenario})")
            rid = str(uuid.uuid4())
            off = mock_log.mark()
            r = httpx.post(f"{proxy.base_url}/chat/completions", timeout=60,
                           headers={"Authorization": f"Bearer {proxy.master_key}"},
                           json={"model": model_group(a.scenario),
                                 "messages": [{"role": "user", "content": f"Update record cust-0001. REQ:{rid}"}]})
            print(f"HTTP {r.status_code}")
            for k in ("x-litellm-model-api-base", "x-litellm-model-group", "x-litellm-attempted-fallbacks"):
                if k in r.headers:
                    print(f"{k}: {r.headers[k]}")
            print(json.dumps(r.json(), indent=1)[:900])

            banner("2. Ground truth from the mock provider (who was actually called)")
            for c in ground_truth(mock_log.since(off), rid)["calls"]:
                print(f"  {c['label']:7s} scenario={c['scenario_id']:24s} status={c['status']} "
                      f"refused={c['refused']} answered={c['answered']}")

            banner("3. Same thing inside an agent (OpenAI Agents SDK, tool: write_record)")
            store = RecordStore(tmp / "records.sqlite")
            ctx = ToolContext(session_id=uuid.uuid4().hex, framework="openai_agents", store=store)
            r1, r2 = str(uuid.uuid4()), str(uuid.uuid4())
            off = mock_log.mark()
            res = asyncio.run(run_openai_agents_session(proxy.base_url, proxy.master_key, model_group(a.scenario),
                                                        turn_prompts(r1, r2)[:1], (r1,), ctx))
            gt = ground_truth(mock_log.since(off), r1)
            t = res.turns[0]
            print(f"agent final output : {t.final_text!r}" + (f"\nagent error        : {t.error}" if t.error else ""))
            print(f"mock calls         : {gt['labels']}  -> answering model: {gt['answering_model']}")
            print(f"tool rows written  : {[w['value'] for w in store.rows(ctx.session_id)]}")
            print(f"trace model fields : {sorted(set(trace_identity_values(strip_content(res.trace_records))))}")
            print(f"gateway said       : {[ (g.status, g.body_model) for g in res.capture.responses]}")


if __name__ == "__main__":
    main()
