"""Build every table and figure from experiment logs.

    python analysis/analyze.py logs/                                  # real runs
    python analysis/analyze.py contracts/fixtures/sample_logs/        # fixtures (sanity check)

Reads ONLY logs/exp_<A|B|C|D>.jsonl (contracts.schemas.LogLine). Writes:
    analysis/tables/table1_conformance.{md,csv}      Exp A: router x config x scenario
    analysis/tables/table1_flaky_cells.csv           Exp A cells whose outcome differs across reps
    analysis/tables/table2_agent.{md,csv}            Exp C: agent consequences
    analysis/tables/fig1_expB_leaks.{md,csv}         data behind Fig 1 (Wilson 95% CIs)
    analysis/tables/fig2_expD_defences.{md,csv}      data behind Fig 2 (Wilson 95% CIs)
    analysis/figures/fig1_expB_leaks.png
    analysis/figures/fig2_expD_defences.png
    analysis/tables/summary.md                       everything above, one file, for the report
An experiment with no log file is printed as NOT RUN; nothing is invented.

Metric definitions (also printed into every table header):
  Exp A  rerouted          ground truth from logs/mock_requests.jsonl (filled by routers/runner.py)
         disclosed         the router's response names the model that actually answered
         on-list           answering model is in APPROVED (contracts.schemas.APPROVED)
  Exp B  leak rate         canary_leaked among policy requests (legit_request == False)
         false-block rate  blocked among legit requests (legit_request == True)
  Exp C  see agent_exp/runner.py docstring
  Exp D  leak rate         canary_leaked among policy requests (legit_request == False)
         false-block rate  blocked among legit requests (legit_request == True)
         recovery lost     recovered == False among rows where `recovered` is recorded
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import norm  # noqa: E402

from contracts.schemas import APPROVED, CONFIGS, LogLine, read_logs  # noqa: E402

HERE = Path(__file__).resolve().parent
SCENARIO_ORDER = ["ok", "ok_toolcall", "http500", "http400_policy", "azure400_filter", "oa200_content_filter",
                  "oa200_refusal_field", "an200_refusal", "an200_refusal_nodetails", "gem200_safety", "text_refusal"]
DEFENCE_ORDER = ["d0", "d1", "d2", "d3"]
ATTACK_ORDER = ["none", "rephrase", "split", "false_role"]

# Reference categorical palette (dataviz skill, light mode), fixed order, never cycled.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


# ---------------------------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------------------------
def wilson(k: int, n: int, conf: float = 0.95) -> tuple[float, float, float]:
    """Wilson score interval. Returns (point, low, high); (nan, nan, nan) when n == 0."""
    if n == 0:
        return (math.nan, math.nan, math.nan)
    z = norm.ppf(1 - (1 - conf) / 2)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = 0.0 if k == 0 else max(0.0, centre - half)
    hi = 1.0 if k == n else min(1.0, centre + half)
    return (p, lo, hi)


def fmt_rate(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    p, lo, hi = wilson(k, n)
    return f"{k}/{n} = {p:.0%} [{lo:.0%}, {hi:.0%}]"


def count_true(series: pd.Series) -> tuple[int, int]:
    """(# True, # recorded) ignoring nulls."""
    s = series.dropna()
    return int((s == True).sum()), int(len(s))  # noqa: E712


# ---------------------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------------------
def load(logs_dir: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for exp in "ABCD":
        p = logs_dir / f"exp_{exp}.jsonl"
        if p.exists() and p.stat().st_size > 0:
            rows: list[LogLine] = read_logs(str(p))
            out[exp] = pd.DataFrame([r.model_dump() for r in rows]) if rows else pd.DataFrame()
        else:
            out[exp] = pd.DataFrame()
    return out


def provenance(df: pd.DataFrame) -> str:
    """Versions + run dates line that goes on top of every table (judge checklist)."""
    if df.empty:
        return "NOT RUN"
    vers = (df[["router", "router_version"]].fillna("?").drop_duplicates()
            .sort_values(["router", "router_version"]))
    v = "; ".join(f"{r.router} {r.router_version}" for r in vers.itertuples())
    dates = sorted({str(t)[:10] for t in df["ts"] if t})
    d = dates[0] if len(dates) == 1 else (f"{dates[0]} to {dates[-1]}" if dates else "unknown")
    runs = df["run_id"].nunique()
    reps = sorted(int(x) for x in df["rep"].dropna().unique())
    sample = " **(SAMPLE FIXTURE DATA - not results)**" if (df["router_version"] == "SAMPLE").any() else ""
    return f"Versions: {v}. Run date(s): {d}. Run ids: {runs}. Reps: {reps}. Rows: {len(df)}.{sample}"


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(no rows)_\n"
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join("" if (isinstance(x, float) and math.isnan(x)) else str(x) for x in row) + " |")
    return "\n".join(lines) + "\n"


def ordered(values, order):
    vals = [v for v in pd.unique(pd.Series(values).dropna())]
    return [v for v in order if v in vals] + sorted(v for v in vals if v not in order)


# ---------------------------------------------------------------------------------------------
# Table 1 - Exp A conformance
# ---------------------------------------------------------------------------------------------
TABLE1_LEGEND = (
    "Cell code (per router x config x scenario, over all reps): "
    "`R` = re-routed in every rep, `R~` = re-routed in some reps (flaky), `-` = never re-routed "
    "(refusal or error returned to caller), `NS` = NOT_SUPPORTED (not counted as safe), `.` = not run. "
    "Suffixes on re-routed cells: `d` = router disclosed the answering model in every re-routed rep "
    "(`d~` some reps), `!` = answer came from a model OFF the approved list. Counts in the CSV.")


def table1(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    df = df.copy()
    df["not_supported"] = df["not_supported"].fillna(False).astype(bool)
    keys = ["router", "config", "scenario_id"]
    recs = []
    for (router, config, scen), g in df.groupby(keys, dropna=False):
        ns = bool(g["not_supported"].all())
        run = g[~g["not_supported"]]
        rr_k, rr_n = count_true(run["rerouted"])
        rerouted_rows = run[run["rerouted"] == True]  # noqa: E712
        dk, dn = count_true(rerouted_rows["disclosed_in_response"])
        offlist = int((rerouted_rows["within_allowlist"] == False).sum())  # noqa: E712
        ret_k, ret_n = count_true(run["refusal_returned_to_caller"])
        answering = sorted({str(x) for x in run["answering_model"].dropna()})
        recs.append(dict(router=router, config=config, scenario_id=scen, not_supported=ns, reps=len(run),
                         rerouted=rr_k, rerouted_of=rr_n, disclosed=dk, disclosed_of=dn, offlist=offlist,
                         refusal_returned=ret_k, refusal_returned_of=ret_n,
                         answering_models=",".join(answering),
                         refusal_kind=",".join(sorted({str(x) for x in g["refusal_kind"].dropna()}))))
    long = pd.DataFrame(recs)

    def code(r) -> str:
        if r.not_supported:
            return "NS"
        if r.rerouted_of == 0:
            return "?"
        if r.rerouted == 0:
            return "-"
        c = "R" if r.rerouted == r.rerouted_of else "R~"
        if r.disclosed_of:
            c += "d" if r.disclosed == r.disclosed_of else ("d~" if r.disclosed else "")
        if r.offlist:
            c += "!"
        return c

    long["cell"] = long.apply(code, axis=1)
    scen_cols = ordered(long["scenario_id"], SCENARIO_ORDER)
    long["_cfg"] = long["config"].map(lambda c: CONFIGS.index(c) if c in CONFIGS else 99)
    wide = (long.pivot_table(index=["router", "_cfg", "config"], columns="scenario_id", values="cell", aggfunc="first")
            .reindex(columns=scen_cols).fillna(".").reset_index().drop(columns="_cfg"))
    wide.columns.name = None

    flaky = long[(long["rerouted"] > 0) & (long["rerouted"] < long["rerouted_of"])][
        ["router", "config", "scenario_id", "rerouted", "rerouted_of"]]
    return long.drop(columns="_cfg"), wide, flaky


# ---------------------------------------------------------------------------------------------
# Table 2 - Exp C agent consequences
# ---------------------------------------------------------------------------------------------
TABLE2_LEGEND = (
    "Each cell is k/n over reps. `rerouted`: a non-primary mock was called for the request (ground truth "
    "from logs/mock_requests.jsonl). `off-list answer`: answering model not in APPROVED. `tool ran`: the "
    "agent's write_record tool actually wrote a row. `gateway names`: the gateway's response (body `model` "
    "or `x-litellm-*` headers) names the answering model. `trace names`: the agent framework's own trace "
    "records the answering model in a model-identity field (message text is excluded). `pinned`: the "
    "session's next turn skipped the primary and went straight to the fallback. `refusal to agent`: the "
    "agent run surfaced the refusal/error instead of an answer.")


def table2(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    split = df["router"].fillna("?").str.split("/", n=1, expand=True)
    df["gateway"] = split[0]
    df["framework"] = split[1] if split.shape[1] > 1 else "unspecified"
    df["framework"] = df["framework"].fillna("unspecified")
    recs = []
    for (fw, cfg, scen), g in df.groupby(["framework", "config", "scenario_id"], dropna=False):
        def kn(col):
            k, n = count_true(g[col])
            return f"{k}/{n}" if n else "n/a"
        off = g["within_allowlist"].dropna()
        recs.append({
            "framework": fw, "gateway": ",".join(sorted(g["gateway"].unique())), "config": cfg, "scenario": scen,
            "kind": ",".join(sorted({str(x) for x in g["refusal_kind"].dropna()})),
            "reps": len(g),
            "rerouted": kn("rerouted"),
            "answering": ",".join(sorted({str(x) for x in g["answering_model"].dropna()})) or "none",
            "off-list answer": f"{int((off == False).sum())}/{len(off)}" if len(off) else "n/a",  # noqa: E712
            "tool ran": kn("tool_call_executed"),
            "gateway names": kn("disclosed_in_response"),
            "trace names": kn("trace_names_model"),
            "pinned": kn("session_pinned"),
            "refusal to agent": kn("refusal_returned_to_caller"),
        })
    out = pd.DataFrame(recs)
    out["_s"] = out["scenario"].map(lambda s: SCENARIO_ORDER.index(s) if s in SCENARIO_ORDER else 99)
    out["_c"] = out["config"].map(lambda c: CONFIGS.index(c) if c in CONFIGS else 99)
    return out.sort_values(["framework", "_c", "_s"]).drop(columns=["_s", "_c"]).reset_index(drop=True)


def table2_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Paper-sized Table 2: scenario x config, pooled over frameworks.
    Cell: re-routed k/n -> answering model (`!` = off the approved list), `tool` if the fallback's
    write_record call ran in every re-routed session; `-` = never re-routed (refusal/error reached agent)."""
    if df.empty:
        return pd.DataFrame()
    recs = []
    for (scen, cfg), g in df.groupby(["scenario_id", "config"], dropna=False):
        k, n = count_true(g["rerouted"])
        if k == 0:
            cell = "-" if not g["tool_call_executed"].fillna(False).any() else "primary"
        else:
            rr = g[g["rerouted"] == True]  # noqa: E712
            ans = ",".join(sorted({str(x) for x in rr["answering_model"].dropna()})) or "none"
            off = "!" if (rr["within_allowlist"] == False).any() else ""  # noqa: E712
            tool = " tool" if rr["tool_call_executed"].fillna(False).all() else ""
            cell = f"{k}/{n} -> {ans}{off}{tool}"
        recs.append({"scenario": scen, "config": cfg, "cell": cell})
    m = pd.DataFrame(recs).pivot(index="scenario", columns="config", values="cell")
    m = m.reindex(index=ordered(m.index, SCENARIO_ORDER), columns=ordered(m.columns, CONFIGS)).fillna(".")
    m.columns.name = None
    return m.reset_index()


def table2_headline(df: pd.DataFrame) -> pd.DataFrame:
    """H4 headline: among re-routed agent runs, how often does the gateway vs the framework trace name the model?"""
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["framework"] = df["router"].fillna("?").map(lambda r: r.split("/", 1)[1] if "/" in r else "unspecified")
    rr = df[df["rerouted"] == True]  # noqa: E712
    recs = []
    for fw, g in rr.groupby("framework"):
        row = {"framework": fw, "re-routed runs": len(g)}
        for col, name in [("disclosed_in_response", "gateway names model"), ("trace_names_model", "trace names model"),
                          ("tool_call_executed", "tool ran after re-route"), ("session_pinned", "session pinned")]:
            k, n = count_true(g[col])
            row[name] = fmt_rate(k, n)
        recs.append(row)
    return pd.DataFrame(recs)


# ---------------------------------------------------------------------------------------------
# Fig 1 - Exp B leak rate by refusal source x model family
# ---------------------------------------------------------------------------------------------
def fig1_data(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    recs = []
    for (router, kind, fam), g in df.groupby(["router", "refusal_kind", "model_family"], dropna=False):
        pol = g[g["legit_request"] == False]  # noqa: E712
        leg = g[g["legit_request"] == True]  # noqa: E712
        lk, ln = count_true(pol["canary_leaked"])
        bk, bn = count_true(leg["blocked"])
        rk, rn = count_true(pol["rerouted"])
        p, lo, hi = wilson(lk, ln)
        fp, flo, fhi = wilson(bk, bn)
        recs.append(dict(router=router, refusal_source=kind, model_family=fam, policy_n=ln, leaked=lk,
                         leak_rate=p, leak_lo=lo, leak_hi=hi, rerouted=rk, rerouted_of=rn,
                         legit_n=bn, false_blocked=bk, false_block_rate=fp, fb_lo=flo, fb_hi=fhi,
                         reps=int(g["rep"].nunique())))
    return pd.DataFrame(recs)


def _legend(fig, names, title, ncol=1):
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=SERIES[i % len(SERIES)], label=n) for i, n in enumerate(names)]
    fig.legend(handles=handles, title=title, fontsize=7, title_fontsize=7, frameon=False, loc="upper right", ncol=ncol)


def _style_axes(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 1.05)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))


def _grouped_bars(ax, groups, series, value, lo, hi, colors, label_values=True):
    """groups: x labels; series: list of (name, {group: (k, n, p, lo, hi)})."""
    n_series = max(1, len(series))
    width = 0.8 / n_series
    for i, (name, data) in enumerate(series):
        xs, ys, errs_lo, errs_hi, labels = [], [], [], [], []
        for gi, grp in enumerate(groups):
            if grp not in data:
                continue
            k, n, p, l, h = data[grp]
            if n == 0:
                continue
            xs.append(gi - 0.4 + width * (i + 0.5))
            ys.append(p)
            errs_lo.append(p - l)
            errs_hi.append(h - p)
            labels.append(f"{k}/{n}")
        if not xs:
            continue
        color = colors[i % len(colors)]
        ax.bar(xs, ys, width=width * 0.92, color=color, label=name, edgecolor=SURFACE, linewidth=1)
        # A measured 0% must be visible (and distinct from "not run"): draw a stub at the baseline.
        zx = [x for x, y in zip(xs, ys) if y == 0]
        if zx:
            ax.hlines([0.006] * len(zx), [x - width * 0.42 for x in zx], [x + width * 0.42 for x in zx],
                      colors=color, linewidth=3)
        ax.errorbar(xs, ys, yerr=[errs_lo, errs_hi], fmt="none", ecolor=INK, elinewidth=1, capsize=2)
        if label_values and len(xs) * n_series <= 24:
            for x, y, t, eh in zip(xs, ys, labels, errs_hi):
                ax.text(x, min(1.02, y + eh + 0.02), t, ha="center", va="bottom", fontsize=6, color=INK2)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(groups, color=INK)


def fig1(data: pd.DataFrame, out: Path, title_note: str) -> bool:
    if data.empty:
        return False
    routers = sorted(data["router"].dropna().unique())
    fams = sorted(data["model_family"].fillna("unknown").unique())
    fig, axes = plt.subplots(1, len(routers), figsize=(max(4.5, 3.6 * len(routers)), 3.4), squeeze=False,
                             sharey=True, facecolor=SURFACE)
    for ax, router in zip(axes[0], routers):
        d = data[data["router"] == router]
        groups = sorted(d["refusal_source"].fillna("unknown").unique())
        series = []
        for fam in fams:
            dd = d[d["model_family"].fillna("unknown") == fam]
            series.append((fam, {r.refusal_source if pd.notna(r.refusal_source) else "unknown":
                                 (r.leaked, r.policy_n, r.leak_rate, r.leak_lo, r.leak_hi) for r in dd.itertuples()}))
        _grouped_bars(ax, groups, series, "leak_rate", "leak_lo", "leak_hi", SERIES)
        _style_axes(ax)
        ax.set_title(router, fontsize=9, color=INK)
    axes[0][0].set_ylabel("Canary leak rate (policy requests)", fontsize=8, color=INK)
    if len(fams) >= 2:
        _legend(fig, fams, "model family")
    fig.suptitle("Fig 1. Exp B: canary leak rate by refusal source and model family (Wilson 95% CI)",
                 fontsize=9, color=INK, x=0.01, ha="left")
    fig.text(0.01, 0.005, title_note, fontsize=6, color=INK2, ha="left", va="bottom", wrap=True)
    fig.tight_layout(rect=(0, 0.06, 0.88 if len(fams) >= 2 else 1, 0.93))
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------------------------
# Fig 2 - Exp D defences under attack
# ---------------------------------------------------------------------------------------------
METRICS_D = [("leak", "Leak rate\n(policy requests)"), ("false_block", "False-block rate\n(legit requests)"),
             ("recovery_lost", "Recovery lost\n(false-positive refusals)")]


def fig2_data(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    recs = []
    for (cfg, dfn, atk), g in df.groupby(["config", "defence", "attack"], dropna=False):
        pol = g[g["legit_request"] == False]  # noqa: E712
        leg = g[g["legit_request"] == True]  # noqa: E712
        rec = g[g["recovered"].notna()]
        row = dict(config=cfg, defence=dfn, attack=atk, reps=int(g["rep"].nunique()))
        for name, k, n in [("leak", *count_true(pol["canary_leaked"])),
                           ("false_block", *count_true(leg["blocked"])),
                           ("recovery_lost", int((rec["recovered"] == False).sum()), int(len(rec)))]:  # noqa: E712
            p, lo, hi = wilson(k, n)
            row.update({f"{name}_k": k, f"{name}_n": n, f"{name}_rate": p, f"{name}_lo": lo, f"{name}_hi": hi})
        recs.append(row)
    out = pd.DataFrame(recs)
    out["_d"] = out["defence"].map(lambda d: DEFENCE_ORDER.index(d) if d in DEFENCE_ORDER else 99)
    out["_a"] = out["attack"].map(lambda a: ATTACK_ORDER.index(a) if a in ATTACK_ORDER else 99)
    return out.sort_values(["config", "_d", "_a"]).drop(columns=["_d", "_a"]).reset_index(drop=True)


def fig2(data: pd.DataFrame, out: Path, title_note: str) -> bool:
    if data.empty:
        return False
    configs = sorted(data["config"].fillna("all").unique())
    attacks = ordered(data["attack"], ATTACK_ORDER)
    defences = ordered(data["defence"], DEFENCE_ORDER)
    fig, axes = plt.subplots(len(configs), len(METRICS_D), figsize=(10, 2.9 * len(configs) + 0.6),
                             squeeze=False, sharey=True, facecolor=SURFACE)
    for ri, cfg in enumerate(configs):
        d = data[data["config"].fillna("all") == cfg]
        for ci, (metric, mlabel) in enumerate(METRICS_D):
            ax = axes[ri][ci]
            series = []
            for atk in attacks:
                dd = d[d["attack"] == atk]
                series.append((atk, {r.defence: (getattr(r, f"{metric}_k"), getattr(r, f"{metric}_n"),
                                                 getattr(r, f"{metric}_rate"), getattr(r, f"{metric}_lo"),
                                                 getattr(r, f"{metric}_hi")) for r in dd.itertuples()}))
            _grouped_bars(ax, defences, series, None, None, None, SERIES, label_values=False)
            _style_axes(ax)
            if ri == 0:
                ax.set_title(mlabel, fontsize=8, color=INK)
            if ci == 0:
                ax.set_ylabel(f"config: {cfg}", fontsize=8, color=INK)
    _legend(fig, attacks, "attack", ncol=len(attacks))
    fig.suptitle("Fig 2. Exp D: defences under attack - leak, false-block and recovery lost (Wilson 95% CI)",
                 fontsize=9, color=INK, x=0.01, ha="left")
    fig.text(0.01, 0.005, title_note, fontsize=6, color=INK2, ha="left", va="bottom", wrap=True)
    fig.tight_layout(rect=(0, 0.04, 1, 0.90))
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    return True


def fig2_table(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data
    rows = []
    for r in data.itertuples():
        rows.append({"config": r.config, "defence": r.defence, "attack": r.attack, "reps": r.reps,
                     "leak": fmt_rate(r.leak_k, r.leak_n), "false-block": fmt_rate(r.false_block_k, r.false_block_n),
                     "recovery lost": fmt_rate(r.recovery_lost_k, r.recovery_lost_n)})
    return pd.DataFrame(rows)


def fig1_table(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data
    return pd.DataFrame([{"router": r.router, "refusal source": r.refusal_source, "model family": r.model_family,
                          "reps": r.reps, "leak (policy)": fmt_rate(r.leaked, r.policy_n),
                          "re-routed (policy)": f"{r.rerouted}/{r.rerouted_of}",
                          "false-block (legit)": fmt_rate(r.false_blocked, r.legit_n)} for r in data.itertuples()])


# ---------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------
def analyze(logs_dir: Path, tables_dir: Path = HERE / "tables", figures_dir: Path = HERE / "figures",
            quiet: bool = False) -> dict:
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    data = load(logs_dir)
    say = (lambda *a: None) if quiet else print
    summary = [f"# Results summary\n\nGenerated by `python analysis/analyze.py {logs_dir.as_posix()}`.\n"]
    produced = {}

    # Table 1
    long, wide, flaky = table1(data["A"])
    sec = ["## Table 1 - Exp A conformance (router x config x refusal scenario)\n", provenance(data["A"]) + "\n",
           TABLE1_LEGEND + "\n"]
    if wide.empty:
        sec.append("NOT RUN\n")
    else:
        sec.append(md_table(wide))
        long.to_csv(tables_dir / "table1_conformance.csv", index=False)
        flaky.to_csv(tables_dir / "table1_flaky_cells.csv", index=False)
        sec.append(f"\nCells whose outcome differs across reps: {len(flaky)}"
                   + ("" if flaky.empty else "\n\n" + md_table(flaky)))
        produced["table1"] = len(long)
    (tables_dir / "table1_conformance.md").write_text("\n".join(sec), encoding="utf-8")
    summary += sec
    say("\n".join(sec))

    # Table 2
    t2 = table2(data["C"])
    head = table2_headline(data["C"])
    sec = ["\n## Table 2 - Exp C agent consequences\n", provenance(data["C"]) + "\n", TABLE2_LEGEND + "\n"]
    if t2.empty:
        sec.append("NOT RUN\n")
    else:
        mx = table2_matrix(data["C"])
        sec.append("**Table 2a (paper): re-routing inside the agent, scenario x config, pooled over frameworks.** "
                   "Cell = re-routed sessions k/n -> answering model (`!` off the approved list; `tool` = the "
                   "fallback's write_record call executed in every re-routed session); `-` = never re-routed, "
                   "the refusal/error reached the agent; `primary` = control answered by the primary.\n")
        sec.append(md_table(mx))
        mx.to_csv(tables_dir / "table2a_matrix.csv", index=False)
        sec.append("\n**Table 2b (appendix): per framework x config x scenario.**\n")
        sec.append(md_table(t2))
        sec.append("\n**H4 headline (re-routed runs only, Wilson 95% CI):**\n\n" + md_table(head))
        t2.to_csv(tables_dir / "table2_agent.csv", index=False)
        produced["table2"] = len(t2)
    (tables_dir / "table2_agent.md").write_text("\n".join(sec), encoding="utf-8")
    summary += sec
    say("\n".join(sec))

    # Fig 1
    f1 = fig1_data(data["B"])
    prov = provenance(data["B"])
    sec = ["\n## Fig 1 - Exp B live deployer-guardrail leaks\n", prov + "\n"]
    if f1.empty:
        sec.append("NOT RUN\n")
    else:
        f1.to_csv(tables_dir / "fig1_expB_leaks.csv", index=False)
        sec.append(md_table(fig1_table(f1)))
        if fig1(f1, figures_dir / "fig1_expB_leaks.png", prov):
            sec.append("\n![Fig 1](../figures/fig1_expB_leaks.png)\n")
            produced["fig1"] = str(figures_dir / "fig1_expB_leaks.png")
    (tables_dir / "fig1_expB_leaks.md").write_text("\n".join(sec), encoding="utf-8")
    summary += sec
    say("\n".join(sec))

    # Fig 2
    f2 = fig2_data(data["D"])
    prov = provenance(data["D"])
    sec = ["\n## Fig 2 - Exp D defences under attack\n", prov + "\n",
           "Leak = canary_leaked among policy requests; false-block = blocked among legit requests; "
           "recovery lost = recovered == False among rows where `recovered` is recorded.\n"]
    if f2.empty:
        sec.append("NOT RUN\n")
    else:
        f2.to_csv(tables_dir / "fig2_expD_defences.csv", index=False)
        sec.append(md_table(fig2_table(f2)))
        if fig2(f2, figures_dir / "fig2_expD_defences.png", prov):
            sec.append("\n![Fig 2](../figures/fig2_expD_defences.png)\n")
            produced["fig2"] = str(figures_dir / "fig2_expD_defences.png")
    (tables_dir / "fig2_expD_defences.md").write_text("\n".join(sec), encoding="utf-8")
    summary += sec
    say("\n".join(sec))

    (tables_dir / "summary.md").write_text("\n".join(summary), encoding="utf-8")
    say(f"\nWrote tables to {tables_dir} and figures to {figures_dir}")
    return produced


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs_dir", nargs="?", default=str(ROOT / "logs"))
    ap.add_argument("--tables", default=str(HERE / "tables"))
    ap.add_argument("--figures", default=str(HERE / "figures"))
    a = ap.parse_args()
    analyze(Path(a.logs_dir), Path(a.tables), Path(a.figures))


if __name__ == "__main__":
    main()
