"""Experiment C - agent consequences of a re-routed refusal.

    python run.py --exp C --reps 3                                  # everything (all configs/frameworks)
    python run.py --exp C --router litellm/langgraph --config content_policy_fallback --scenario an200_refusal --reps 1
    python -m agent_exp.runner --configs default content_policy_fallback --frameworks openai_agents --reps 3

Setup per session: agent (OpenAI Agents SDK or LangGraph) -> LiteLLM proxy (base_url) -> mock provider.
Primary model group `agent-<scenario>` is mock-a serving the refusal scenario; the fallback group is
mock-b (approved) or mock-z (off-list) serving `ok_toolcall` (it asks the agent to run write_record).
Each session has two user turns with different REQ ids (turn 2 checks session pinning).

LogLine fields written (logs/exp_C.jsonl), all about TURN 1 unless stated:
  router                     "litellm/<framework>"
  router_version             "litellm <v>; <framework versions>"
  rerouted                   mock log shows a non-primary label called for the turn-1 REQ id
  answering_model            last mock label that produced a real answer for turn 1 (mock log)
  within_allowlist           answering_model in APPROVED
  reported_model             `model` field of the first 200 response the gateway returned to the agent
  disclosed_in_response      a 200 gateway response (body `model` or any x-litellm-* header) names the
                             answering model
  tool_call_executed         the write_record tool really wrote a row for turn 1 (SQLite)
  trace_names_model          the framework's own trace names the answering model in a model-identity
                             field (content, tool args and base URLs excluded) - see agent_exp/common.py
  session_pinned             (only if turn 1 was re-routed) turn 2 never called the primary and did
                             call a fallback
  refusal_returned_to_caller turn 1 raised an error to the agent, or ended with no tool write and no
                             answer text from any model
Per-session evidence (mock calls, gateway headers, trace identity values, outputs, errors) goes to
logs/exp_C_details.jsonl so every LogLine can be audited.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.schemas import LogLine, now_iso, write_log  # noqa: E402
from agent_exp.common import (EXP_C_SCENARIOS, FRAMEWORKS, MockLog, RecordStore, ToolContext,  # noqa: E402
                              ground_truth, names_label, scenario_kinds, trace_identity_values,
                              strip_content, trace_names_label, turn_prompts, within_allowlist)
from agent_exp.frameworks import RUNNERS, SessionResult  # noqa: E402
from agent_exp.gateway import EXP_C_CONFIGS, LiteLLMProxy, MockServer, litellm_version, model_group  # noqa: E402

DEFAULT_MOCK_URL = os.environ.get("MOCK_URL", "http://localhost:8900")


def evaluate(session: SessionResult, calls: list[dict], rid1: str, rid2: str, store: RecordStore,
             session_id: str) -> tuple[dict, dict]:
    """Turn raw evidence into LogLine outcome fields + an audit record."""
    gt1, gt2 = ground_truth(calls, rid1), ground_truth(calls, rid2)
    writes = store.rows(session_id)
    w1 = [w for w in writes if w["request_id"] == rid1]
    t1 = session.turns[0] if session.turns else None
    t2 = session.turns[1] if len(session.turns) > 1 else None
    answering = gt1["answering_model"]
    gw1 = session.capture.for_request(rid1)
    ok1 = [r for r in gw1 if r.status == 200]

    disclosed = None if answering is None else any(names_label(r, answering) for r in ok1)
    trace_names = None if answering is None else trace_names_label(session.trace_records, answering)
    pinned = None
    if gt1["rerouted"] and t2 is not None:
        pinned = gt2["primary_calls"] == 0 and len(gt2["labels"]) > 0
    final1 = (t1.final_text or "") if t1 else ""
    refusal_to_caller = bool(t1 is None or t1.error or (not w1 and "ANSWERED_BY=" not in final1))

    outcome = dict(
        rerouted=gt1["rerouted"] if gt1["labels"] else None,
        answering_model=answering,
        reported_model=ok1[0].body_model if ok1 else None,
        disclosed_in_response=disclosed,
        within_allowlist=within_allowlist(answering),
        refusal_returned_to_caller=refusal_to_caller,
        tool_call_executed=bool(w1),
        trace_names_model=trace_names,
        session_pinned=pinned,
    )
    audit = dict(
        mock_calls_turn1=gt1["calls"], mock_calls_turn2=gt2["calls"],
        gateway_turn1=[r.__dict__ for r in gw1], gateway_turn2=[r.__dict__ for r in session.capture.for_request(rid2)],
        tool_writes=writes,
        trace_identity_values=sorted(set(trace_identity_values(strip_content(session.trace_records)))),
        trace_record_count=len(session.trace_records),
        turns=[t.__dict__ for t in session.turns],
    )
    return outcome, audit


async def run_session(framework: str, base_url: str, api_key: str, scenario: str, store: RecordStore,
                      mock_log: MockLog, http_client=None) -> tuple[str, str, str, SessionResult, list[dict]]:
    rid1, rid2 = str(uuid.uuid4()), str(uuid.uuid4())
    session_id = uuid.uuid4().hex
    ctx = ToolContext(session_id=session_id, framework=framework, store=store)
    offset = mock_log.mark()
    session = await RUNNERS[framework](base_url, api_key, model_group(scenario), turn_prompts(rid1, rid2),
                                       (rid1, rid2), ctx, http_client=http_client)
    calls = mock_log.since(offset)
    return rid1, rid2, session_id, session, calls


def run(configs: list[str], frameworks: list[str], scenarios: list[str], reps: int, run_id: str,
        mock_url: str = DEFAULT_MOCK_URL, logs_dir: Path = ROOT / "logs", proxy_port: int = 4100,
        mock_log_path: Path | None = None) -> int:
    kinds = scenario_kinds()
    logs_dir.mkdir(parents=True, exist_ok=True)
    work = logs_dir / "exp_C_work"
    store = RecordStore(logs_dir / "exp_C_records.sqlite")
    lv = litellm_version()
    from agent_exp.frameworks import framework_version
    n = 0
    with MockServer(mock_url, logs_dir):
        # Ground truth must come from the file the running mock actually writes to.
        import httpx
        served_log = httpx.get(f"{mock_url.rstrip('/')}/health", timeout=5).json().get("log_path")
        mock_log = MockLog(mock_log_path or Path(served_log))
        print(f"[exp C] mock ground-truth log: {mock_log.path}", flush=True)
        for config in configs:
            print(f"[exp C] starting LiteLLM {lv} proxy for config={config} ...", flush=True)
            with LiteLLMProxy(config, mock_url, proxy_port, work) as proxy:
                for framework in frameworks:
                    fv = framework_version(framework)
                    for scenario in scenarios:
                        for rep in range(reps):
                            rid1, rid2, sid, session, calls = asyncio.run(
                                run_session(framework, proxy.base_url, proxy.master_key, scenario, store, mock_log))
                            outcome, audit = evaluate(session, calls, rid1, rid2, store, sid)
                            line = LogLine(exp="C", run_id=run_id, request_id=rid1, rep=rep,
                                           router=f"litellm/{framework}", router_version=f"litellm {lv}; {fv}",
                                           config=config, scenario_id=scenario, refusal_kind=kinds.get(scenario),
                                           **outcome)
                            write_log(line, str(logs_dir))
                            with open(logs_dir / "exp_C_details.jsonl", "a", encoding="utf-8") as f:
                                f.write(json.dumps({"run_id": run_id, "request_id": rid1, "turn2_request_id": rid2,
                                                    "session_id": sid, "framework": framework, "config": config,
                                                    "scenario_id": scenario, "rep": rep, "ts": now_iso(),
                                                    "outcome": outcome, **audit}, default=str) + "\n")
                            n += 1
                            print(f"[exp C] {config:26s} {framework:13s} {scenario:24s} rep{rep} "
                                  f"rerouted={outcome['rerouted']} ans={outcome['answering_model']} "
                                  f"tool={outcome['tool_call_executed']} gw={outcome['disclosed_in_response']} "
                                  f"trace={outcome['trace_names_model']} pinned={outcome['session_pinned']} "
                                  f"refusal->agent={outcome['refusal_returned_to_caller']}", flush=True)
    print(f"[exp C] wrote {n} LogLines to {logs_dir / 'exp_C.jsonl'} (run_id={run_id})")
    return n


def _parse_router(router: str | None) -> list[str]:
    if not router or router == "litellm":
        return list(FRAMEWORKS)
    gw, _, fw = router.partition("/")
    if gw != "litellm":
        sys.exit(f"Exp C uses LiteLLM as the agent gateway; got router={router!r}")
    if fw not in FRAMEWORKS:
        sys.exit(f"unknown framework {fw!r}; choose from {FRAMEWORKS}")
    return [fw]


def main(run_id: str | None = None, router: str | None = None, config: str | None = None,
         scenario: str | None = None, reps: int = 1, **_) -> None:
    """Entry point used by run.py (--exp C)."""
    configs = [config] if config else list(EXP_C_CONFIGS)
    for c in configs:
        if c not in EXP_C_CONFIGS:
            sys.exit(f"Exp C config {c!r} not defined; choose from {EXP_C_CONFIGS}")
    scenarios = [scenario] if scenario else list(EXP_C_SCENARIOS)
    run(configs, _parse_router(router), scenarios, reps, run_id or uuid.uuid4().hex)


def cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--configs", nargs="+", default=list(EXP_C_CONFIGS), choices=EXP_C_CONFIGS)
    ap.add_argument("--frameworks", nargs="+", default=list(FRAMEWORKS), choices=FRAMEWORKS)
    ap.add_argument("--scenarios", nargs="+", default=list(EXP_C_SCENARIOS), choices=EXP_C_SCENARIOS)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--mock-url", default=DEFAULT_MOCK_URL)
    ap.add_argument("--proxy-port", type=int, default=4100)
    ap.add_argument("--logs-dir", default=str(ROOT / "logs"))
    a = ap.parse_args()
    run(a.configs, a.frameworks, a.scenarios, a.reps, uuid.uuid4().hex, a.mock_url, Path(a.logs_dir), a.proxy_port)


if __name__ == "__main__":
    cli()
