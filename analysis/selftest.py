"""analysis selftest. No network, no keys, < 30 s. Writes only to a temp dir.

1. Wilson interval matches reference values.
2. Exp A cell codes: A / H / R(b) / R(z) / NS / ERR / '!' (differed across reps), ok_toolcall scored A.
3. Filters: excluded Exp A run_id dropped; default+deployer_guardrail relabelled guardrail_control;
   Exp B provider_error rows dropped.
4. analyze() on contracts/fixtures/sample_logs builds table1.md/.png, table2.md, fig1.png, fig2.png and
   RESULTS.md (marked SAMPLE); an empty logs dir yields NOT RUN everywhere and no figures.
"""
from __future__ import annotations

import math
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from analysis.analyze import EXCLUDED_A_RUNS, analyze, filter_A, filter_B, table1, wilson  # noqa: E402
from contracts.schemas import LogLine  # noqa: E402

SAMPLES = ROOT / "contracts" / "fixtures" / "sample_logs"


def L(**kw) -> dict:
    base = dict(exp="A", run_id="t", request_id="r", rep=0, router="x", router_version="1", config="default",
                scenario_id="ok", ts="2026-11-08T00:00:00Z")
    base.update(kw)
    return LogLine(**base).model_dump()


def check_wilson():
    _, lo, hi = wilson(5, 10)
    assert abs(lo - 0.2366) < 1e-3 and abs(hi - 0.7634) < 1e-3, (lo, hi)
    _, lo, hi = wilson(0, 10)
    assert lo == 0.0 and abs(hi - 0.2775) < 1e-3
    _, lo, hi = wilson(10, 10)
    assert hi == 1.0 and abs(lo - 0.7225) < 1e-3
    assert all(math.isnan(x) for x in wilson(0, 0))


def check_codes_and_filters():
    rows = []
    for rep in range(3):  # R(b) every rep
        rows.append(L(rep=rep, config="outage_fallback", scenario_id="http500", rerouted=True, answering_model="mock-b",
                      within_allowlist=True, not_supported=False))
        rows.append(L(rep=rep, config="offlist_fallback", scenario_id="http500", rerouted=True, answering_model="mock-z",
                      within_allowlist=False, not_supported=False))
        rows.append(L(rep=rep, config="default", scenario_id="ok_toolcall", rerouted=False, answering_model=None,
                      refusal_returned_to_caller=True, not_supported=False))
        rows.append(L(rep=rep, config="default", scenario_id="oa200_content_filter", rerouted=rep == 1,
                      answering_model="mock-b" if rep == 1 else None, not_supported=False))
        rows.append(L(rep=rep, config="refusal_failover", scenario_id="ok", not_supported=True))
        rows.append(L(rep=rep, config="default", scenario_id="text_refusal", rerouted=None, not_supported=False))
        for legit in (False, True):
            rows.append(L(rep=rep, config="default", scenario_id="ok", refusal_kind="deployer_guardrail",
                          legit_request=legit, rerouted=False, answering_model="mock-a" if legit else None,
                          blocked=not legit, not_supported=False))
    rows.append(L(run_id=next(iter(EXCLUDED_A_RUNS)), config="default", scenario_id="http500", not_supported=False))
    df, info = filter_A(pd.DataFrame(rows))
    assert info["rows_excluded"] == 1 and info["relabelled_guardrail_control"] == 6, info
    main, gr, long = table1(df)
    m = main.set_index("config")
    assert m.loc["outage_fallback", "http500"] == "R(b)"
    assert m.loc["offlist_fallback", "http500"] == "R(z)"
    assert m.loc["default", "ok_toolcall"] == "A"
    assert m.loc["default", "oa200_content_filter"] == "H!"
    assert m.loc["refusal_failover", "ok"] == "NS"
    assert m.loc["default", "text_refusal"] == "ERR"
    g = gr.set_index("config")
    assert g.loc["guardrail_control", "blocked prompt"] == "H" and g.loc["guardrail_control", "allowed prompt"] == "A"

    # Cross-check: Exp C cells compared with Exp A's litellm cells; known setup differences are explained.
    from analysis.analyze import crosscheck_A_C
    la = pd.DataFrame([dict(kind="scenario", router="litellm", config="outage_fallback", column="http500", code="R(b)"),
                       dict(kind="scenario", router="litellm", config="content_policy_fallback", column="azure400_filter", code="H"),
                       dict(kind="scenario", router="litellm", config="default", column="http500", code="H")])
    c = pd.DataFrame([L(exp="C", router="litellm/x", config="outage_fallback", scenario_id="http500", rerouted=True, answering_model="mock-b"),
                      L(exp="C", router="litellm/x", config="content_policy_fallback", scenario_id="azure400_filter", rerouted=True, answering_model="mock-b"),
                      L(exp="C", router="litellm/x", config="default", scenario_id="http500", rerouted=False, tool_call_executed=False)])
    x = crosscheck_A_C(la, c).set_index(["config", "scenario"])["verdict"]
    assert x[("outage_fallback", "http500")] == "agree" and x[("default", "http500")] == "agree"
    assert x[("content_policy_fallback", "azure400_filter")] == "differ (explained)"

    b = pd.DataFrame([L(exp="B", refusal_kind="provider_error", legit_request=False),
                      L(exp="B", refusal_kind="deployer_guardrail", legit_request=False, rerouted=True)])
    bf, binfo = filter_B(b)
    assert len(bf) == 1 and binfo["rows_excluded"] == 1


def main():
    t0 = time.perf_counter()
    check_wilson()
    check_codes_and_filters()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        produced = analyze(SAMPLES, tmp / "tables", tmp / "figures", tmp / "RESULTS.md", quiet=True)
        for key in ("table1", "table2", "fig1", "fig2", "results"):
            assert key in produced, (key, produced)
        for f in ("tables/table1.md", "tables/table2.md", "RESULTS.md"):
            assert (tmp / f).exists(), f
        for f in ("table1.png", "fig1.png", "fig2.png"):
            assert (tmp / "figures" / f).stat().st_size > 10_000, f
        res = (tmp / "RESULTS.md").read_text(encoding="utf-8")
        assert "SAMPLE FIXTURE DATA" in res and "95% CI" in res and "Filters applied" in res

        empty = tmp / "empty"
        empty.mkdir()
        produced = analyze(empty, tmp / "t2", tmp / "f2", tmp / "R2.md", quiet=True)
        assert set(produced) == {"results"}, produced
        assert (tmp / "R2.md").read_text(encoding="utf-8").count("NOT RUN") >= 4
        assert not any((tmp / "f2").iterdir())
    print(f"analysis OK (Wilson CI, cell codes A/H/R(b)/R(z)/NS/ERR/!, filters, all outputs from sample logs, "
          f"empty logs -> NOT RUN; {time.perf_counter() - t0:.1f}s)")


if __name__ == "__main__":
    main()
