"""Experiment A: router x config x scenario x rep. Outcomes come from the mock's log, not the router."""
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional
from uuid import uuid4

from contracts.schemas import APPROVED, CONFIGS, PRIMARY, LogLine, RouterResult, write_log
from routers.common import GUARDRAIL_CONTROL, SCENARIO_STYLE, make_prompt, short_error
from routers.guardrail_policy import blocked_prompt
from routers.registry import ADAPTERS

ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs"
SCENARIOS_FILE = ROOT / "contracts" / "scenarios.json"
ANSWER_RE = re.compile(r"ANSWERED_BY=(\S+)")
# Comma-separated scenarios the provider serves, or "*" for all (use "*" with Role A's full mock).
AVAILABLE_SCENARIOS = os.environ.get("AVAILABLE_SCENARIOS", "ok,http500,http400_policy")
GUARDRAIL_CONFIGS = ("guardrail_fallback", GUARDRAIL_CONTROL)
GUARDRAIL_STATUS = 446  # Portkey's deny status.
PROMPTS = {"plain": make_prompt, "allowed": make_prompt, "blocked": blocked_prompt}


def load_scenarios() -> dict[str, str]:
    """Return {scenario id: kind} from the frozen contract."""
    data = json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))
    return {s["id"]: s["kind"] for s in data["scenarios"]}


def labels_hit(request_id: str) -> list[str]:
    """Return the mock labels this request reached, in order."""
    path = LOGS_DIR / "mock_requests.jsonl"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    return [e["label"] for e in entries if e.get("request_id") == request_id]


def outcomes(result: RouterResult, hits: list[str]) -> dict:
    """Compute the outcome fields of a LogLine from ground truth."""
    match = ANSWER_RE.search(result.final_text or "")
    answering = match.group(1) if match else None
    rerouted = any(label != PRIMARY for label in hits)
    return {
        "rerouted": rerouted,
        "answering_model": answering,
        "reported_model": result.reported_model,
        "within_allowlist": answering in APPROVED if answering else None,
        # Needs an answering model: None == None would otherwise count as disclosed.
        "disclosed_in_response": names_model(result, answering) if rerouted and answering else None,
        "refusal_returned_to_caller": answering is None,
    }


def names_model(result: RouterResult, model: str) -> bool:
    """Return True if the body's model field or a router header names the model."""
    return result.reported_model == model or any(model in value for value in result.headers.values())


def cell_fields(result: RouterResult, hits: list[str], kind: str) -> tuple[dict, Optional[str]]:
    """Turn a result into LogLine fields, or a failure note when there is no ground truth."""
    if not hits and not (kind == "blocked" and result.http_status == GUARDRAIL_STATUS):
        return {}, result.error or "router returned without reaching the provider"
    fields = outcomes(result, hits)
    if kind != "plain":  # No model received the request means the block held.
        fields.update(legit_request=kind == "allowed", blocked=not hits)
    return fields, None


def run_cell(adapter, scenario: str, kind: str, request_id: str) -> tuple[dict, Optional[str], Optional[RouterResult]]:
    """Run one cell on a started adapter; a failure never reaches the loop."""
    try:
        adapter.set_scenario(scenario)
        result = adapter.send(PROMPTS[kind](request_id), request_id, SCENARIO_STYLE[scenario])
    except Exception as exc:
        return {}, short_error(exc), None
    return (*cell_fields(result, labels_hit(request_id), kind), result)


def cells(config: str, scenarios: list[str]) -> list[tuple[str, str]]:
    """Return (scenario, prompt kind) pairs; guardrail configs use the ok upstream with both prompts."""
    if config in GUARDRAIL_CONFIGS:
        return [("ok", "blocked"), ("ok", "allowed")] if "ok" in scenarios else []
    return [(s, "plain") for s in scenarios]


def start_adapter(adapter, config: str, mock_url: str) -> Optional[str]:
    """Start a supporting adapter and return an error note if that fails."""
    try:
        if adapter.supports(config):
            adapter.start(config, mock_url)
    except Exception as exc:
        return short_error(exc)
    return None


def pick(value: Optional[str], allowed, what: str) -> list[str]:
    """Expand None to all allowed names, or reject a name not on the allowlist."""
    if value is None:
        return list(allowed)
    if value not in allowed:
        sys.exit(f"Unknown {what} {value!r}. Allowed: {', '.join(allowed)}")
    return [value]


def served(scenarios: list[str]) -> list[str]:
    """Drop scenarios the current provider cannot serve, saying so."""
    available = AVAILABLE_SCENARIOS.split(",")
    kept = [s for s in scenarios if AVAILABLE_SCENARIOS == "*" or s in available]
    for s in sorted(set(scenarios) - set(kept)):
        print(f"SKIPPED: not served by current provider: {s}")
    return kept


def print_table(rows: list[tuple]) -> None:
    header = ("router", "config", "scenario", "rerouted", "answering_model", "disclosed", "status")
    text = [[str(c) for c in r] for r in [header, *rows]]
    widths = [max(len(r[i]) for r in text) for i in range(len(header))]
    for r in text:
        print(" | ".join(c.ljust(w) for c, w in zip(r, widths)))


def main(run_id: str, router: Optional[str] = None, config: Optional[str] = None,
         scenario: Optional[str] = None, reps: int = 1, mock_url: Optional[str] = None) -> None:
    """Run the selected cells and append one LogLine per cell to logs/exp_A.jsonl."""
    kinds = load_scenarios()
    routers = pick(router, list(ADAPTERS), "router")
    configs = pick(config, [*CONFIGS, GUARDRAIL_CONTROL], "config")
    scenarios = served(pick(scenario, list(kinds), "scenario"))
    mock_url = mock_url or os.environ.get("MOCK_URL", "http://127.0.0.1:8900")

    rows, failures = [], []
    for r in routers:
        for c in configs:
            adapter = ADAPTERS[r]()
            try:
                start_error = start_adapter(adapter, c, mock_url)
                for s, kind in cells(c, scenarios):
                    label = s if kind == "plain" else f"{s}/{kind}"
                    for rep in range(reps):
                        request_id = uuid4().hex
                        fields, failure, result = {}, start_error, None
                        unsupported = not adapter.supports_cell(c, s)
                        if not unsupported and not start_error:
                            fields, failure, result = run_cell(adapter, s, kind, request_id)
                        write_log(LogLine(exp="A", run_id=run_id, request_id=request_id, rep=rep, router=r,
                                          router_version=ADAPTERS[r].version,
                                          config="default" if c == GUARDRAIL_CONTROL else c, scenario_id=s,
                                          refusal_kind=kinds[s] if kind == "plain" else "deployer_guardrail",
                                          not_supported=unsupported or None, **fields),
                                  str(LOGS_DIR))
                        rows.append((r, c, label, "NOT_SUPPORTED" if unsupported else fields.get("rerouted"),
                                     fields.get("answering_model"), fields.get("disclosed_in_response"),
                                     result.http_status if result else None))
                        if failure:
                            failures.append(f"NO_RESULT {r} {c} {label} rep{rep}: {failure}")
                        if result and kind != "plain":
                            failures.append(f"HEADERS {r} {c} {label}: {result.headers}")
            finally:
                adapter.stop()
    if rows:
        print_table(rows)
    for failure in failures:
        print(failure)
