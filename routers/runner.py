"""Experiment A: router x config x scenario x rep. Outcomes come from the mock's log, not the router."""
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional
from uuid import uuid4

from contracts.schemas import APPROVED, CONFIGS, PRIMARY, LogLine, RouterResult, write_log
from routers.common import make_prompt, short_error
from routers.registry import ADAPTERS

ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs"
SCENARIOS_FILE = ROOT / "contracts" / "scenarios.json"
ANSWER_RE = re.compile(r"ANSWERED_BY=(\S+)")
# Comma-separated scenarios the provider serves, or "*" for all (use "*" with Role A's full mock).
AVAILABLE_SCENARIOS = os.environ.get("AVAILABLE_SCENARIOS", "ok,http500,http400_policy")


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
        "disclosed_in_response": result.reported_model == answering if rerouted and answering else None,
        "refusal_returned_to_caller": answering is None,
    }


def run_cell(router: str, config: str, scenario: str, request_id: str, mock_url: str) -> tuple[dict, Optional[str]]:
    """Run one cell. Returns (outcome fields, failure note); a failure never reaches the loop."""
    adapter = ADAPTERS[router]()
    try:
        adapter.start(config, mock_url)
        adapter.set_scenario(scenario)
        result = adapter.send(make_prompt(request_id), request_id)
    except Exception as exc:
        return {}, short_error(exc)
    finally:
        adapter.stop()
    hits = labels_hit(request_id)
    if not hits:  # The provider was never reached, so there is no ground truth to report.
        return {}, result.error or "router returned without reaching the provider"
    return outcomes(result, hits), None


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
    header = ("router", "config", "scenario", "rerouted", "answering_model", "disclosed")
    text = [[str(c) for c in r] for r in [header, *rows]]
    widths = [max(len(r[i]) for r in text) for i in range(len(header))]
    for r in text:
        print(" | ".join(c.ljust(w) for c, w in zip(r, widths)))


def main(run_id: str, router: Optional[str] = None, config: Optional[str] = None,
         scenario: Optional[str] = None, reps: int = 1, mock_url: Optional[str] = None) -> None:
    """Run the selected cells and append one LogLine per cell to logs/exp_A.jsonl."""
    kinds = load_scenarios()
    routers = pick(router, list(ADAPTERS), "router")
    configs = pick(config, CONFIGS, "config")
    scenarios = served(pick(scenario, list(kinds), "scenario"))
    mock_url = mock_url or os.environ.get("MOCK_URL", "http://127.0.0.1:8900")

    rows, failures = [], []
    for r in routers:
        for c in configs:
            for s in scenarios:
                for rep in range(reps):
                    request_id = uuid4().hex
                    fields, failure = {}, None
                    unsupported = not ADAPTERS[r]().supports(c)
                    if not unsupported:
                        fields, failure = run_cell(r, c, s, request_id, mock_url)
                    write_log(LogLine(exp="A", run_id=run_id, request_id=request_id, rep=rep, router=r,
                                      router_version=ADAPTERS[r].version, config=c, scenario_id=s,
                                      refusal_kind=kinds[s], not_supported=unsupported or None, **fields),
                              str(LOGS_DIR))
                    rows.append((r, c, s, "NOT_SUPPORTED" if unsupported else fields.get("rerouted"),
                                 fields.get("answering_model"), fields.get("disclosed_in_response")))
                    if failure:
                        failures.append(f"NO_RESULT {r} {c} {s} rep{rep}: {failure}")
    if rows:
        print_table(rows)
    for failure in failures:
        print(failure)
