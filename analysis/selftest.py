"""analysis selftest. No network, no keys, < 30 s.

1. Wilson interval matches known reference values.
2. analyze() on contracts/fixtures/sample_logs builds Table 1, Table 2, Fig 1, Fig 2 (+ CSV/MD) and marks
   the output as SAMPLE data.
3. NOT_SUPPORTED cells render as NS (never as safe); flaky cells (outcome differs across reps) are
   detected; an empty logs dir yields NOT RUN for every experiment, never invented numbers.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.analyze import analyze, table1, wilson  # noqa: E402
from contracts.schemas import LogLine  # noqa: E402

SAMPLES = ROOT / "contracts" / "fixtures" / "sample_logs"


def check_wilson():
    p, lo, hi = wilson(5, 10)
    assert abs(lo - 0.2366) < 1e-3 and abs(hi - 0.7634) < 1e-3, (lo, hi)
    p, lo, hi = wilson(0, 10)
    assert lo == 0.0 and abs(hi - 0.2775) < 1e-3, hi
    p, lo, hi = wilson(10, 10)
    assert hi == 1.0 and abs(lo - 0.7225) < 1e-3, lo
    assert all(math.isnan(x) for x in wilson(0, 0))


def check_table1_logic():
    import pandas as pd
    rows = []
    for rep, rr in enumerate([True, False, True]):
        rows.append(LogLine(exp="A", run_id="t", request_id=f"r{rep}", rep=rep, router="x", router_version="1",
                            config="content_policy_fallback", scenario_id="oa200_content_filter",
                            rerouted=rr, answering_model="mock-z" if rr else None,
                            within_allowlist=False if rr else None, disclosed_in_response=False,
                            not_supported=False, ts="2026-11-08T00:00:00Z").model_dump())
    rows.append(LogLine(exp="A", run_id="t", request_id="ns", rep=0, router="x", router_version="1",
                        config="guardrail_fallback", scenario_id="ok", not_supported=True,
                        ts="2026-11-08T00:00:00Z").model_dump())
    long, wide, flaky = table1(pd.DataFrame(rows))
    cell = wide.set_index("config").loc["content_policy_fallback", "oa200_content_filter"]
    assert cell == "R~!", cell
    assert wide.set_index("config").loc["guardrail_fallback", "ok"] == "NS"
    assert len(flaky) == 1 and int(flaky.iloc[0]["rerouted"]) == 2


def main():
    t0 = time.perf_counter()
    check_wilson()
    check_table1_logic()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        produced = analyze(SAMPLES, tmp / "tables", tmp / "figures", quiet=True)
        for key in ("table1", "table2", "fig1", "fig2"):
            assert key in produced, (key, produced)
        for f in ("table1_conformance.md", "table1_conformance.csv", "table2_agent.md", "table2_agent.csv",
                  "fig1_expB_leaks.csv", "fig2_expD_defences.csv", "summary.md"):
            assert (tmp / "tables" / f).exists(), f
        for f in ("fig1_expB_leaks.png", "fig2_expD_defences.png"):
            assert (tmp / "figures" / f).stat().st_size > 10_000, f
        summary = (tmp / "tables" / "summary.md").read_text(encoding="utf-8")
        assert "SAMPLE FIXTURE DATA" in summary and "NS" in summary and "Wilson" in summary

        empty = tmp / "empty_logs"
        empty.mkdir()
        produced = analyze(empty, tmp / "t2", tmp / "f2", quiet=True)
        assert produced == {}, produced
        s2 = (tmp / "t2" / "summary.md").read_text(encoding="utf-8")
        assert s2.count("NOT RUN") >= 8, s2   # provenance line + body for each of the 4 outputs
    n = sum(1 for p in SAMPLES.glob("exp_*.jsonl") for l in p.read_text(encoding="utf-8").splitlines() if l.strip())
    print(f"analysis OK (Wilson CI verified, NS/flaky/off-list cell codes verified, Table 1/2 + Fig 1/2 built "
          f"from {n} sample LogLines, empty logs -> NOT RUN; {time.perf_counter() - t0:.1f}s)")


if __name__ == "__main__":
    main()
