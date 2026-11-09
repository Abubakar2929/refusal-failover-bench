"""Build every table, figure and the numbers file from the experiment logs. One command:

    python analysis/analyze.py logs/                                  # final runs
    python analysis/analyze.py contracts/fixtures/sample_logs/        # fixtures (sanity check only)

Reads ONLY <logs>/exp_<A|B|C|D>.jsonl (contracts.schemas.LogLine). Log files are never modified; every
exclusion or relabel is applied in code below (FILTERS) and written into analysis/RESULTS.md.

Writes
    analysis/tables/table1.md       Exp A conformance: router x config x scenario (+ deployer-guardrail rows)
    analysis/figures/table1.png     the same table as an image
    analysis/tables/table2.md       Exp C agent consequences: framework x scenario (+ per-config matrix)
    analysis/figures/fig1.png       Exp B (deny prompts): re-routed and leaked rate per fallback model
    analysis/figures/fig2.png       Exp D: leak / false-block / recovery-lost per defence x attack
    analysis/RESULTS.md             every number the report needs, with n, Wilson 95% CI, filters, versions
An experiment with no log is reported as NOT RUN; nothing is invented.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import norm  # noqa: E402

from contracts.schemas import APPROVED, CONFIGS, LogLine, read_logs  # noqa: E402

HERE = Path(__file__).resolve().parent
SCENARIOS_JSON = ROOT / "contracts" / "scenarios.json"
VERSIONS_MD = ROOT / "routers" / "VERSIONS.md"

SCENARIO_ORDER = ["ok", "ok_toolcall", "http500", "http400_policy", "azure400_filter", "oa200_content_filter",
                  "oa200_refusal_field", "text_refusal", "an200_refusal", "an200_refusal_nodetails", "gem200_safety"]
CONFIG_ORDER = CONFIGS + ["guardrail_fallback", "guardrail_control"]
ROUTER_ORDER = ["litellm", "litellm_proxy", "langchain", "portkey"]
DEFENCE_ORDER = ["d0", "d1", "d2", "d3"]
ATTACK_ORDER = ["none", "rephrase", "split", "false_role"]
CONTROL_SCENARIOS = {"ok", "ok_toolcall", "http500"}

# ---------------------------------------------------------------------------------------------
# Filters (applied in code, documented in RESULTS.md). Keys are what RESULTS.md prints.
# ---------------------------------------------------------------------------------------------
EXCLUDED_A_RUNS = {
    "7b64ebc7022c41b6b846f844ac2c6586":
        "48 rows from a LiteLLM-proxy run whose proxy never started (console-encoding crash); executed cells "
        "have null outcomes (routers/STATUS.md, routers/FINDINGS.md)",
}
EXCLUDED_B_KINDS = {
    "provider_error": "call failed upstream (HTTP status other than 200/446, transport error, or 429 after "
                      "retries); no guardrail or routing outcome to measure (routers/STATUS.md, Exp B runner)",
}
FILTERS = {
    "A": [
        f"Excluded run_id {rid}: {why}." for rid, why in EXCLUDED_A_RUNS.items()
    ] + [
        "Controls, not refusals: scenarios `ok`, `ok_toolcall` and `http500` are reported separately and never "
        "counted as held refusals.",
        "`ok_toolcall` rows carry `answering_model=null` and `refusal_returned_to_caller=true` because the runner "
        "reads ANSWERED_BY from message text and a tool call has none; mock-a answered. A non-rerouted "
        "`ok_toolcall` row is therefore scored `A` (primary answered), not `H`.",
        "Deployer-guardrail control rows are logged as `config=\"default\"` with "
        "`refusal_kind=\"deployer_guardrail\"`; they are relabelled `guardrail_control`. In guardrail rows "
        "`legit_request=false` is the blocked prompt and `legit_request=true` the allowed prompt.",
    ],
    "B": [
        f"Excluded rows with refusal_kind=\"{k}\": {why}." for k, why in EXCLUDED_B_KINDS.items()
    ] + [
        "Fig 1 uses deny prompts only (`legit_request=false`), split by the model that answered.",
        "No false-block rate is reported for legit prompts: most `blocked=true` legit rows are empty responses "
        "from the reasoning fallback model, not guardrail blocks (reported as a limitation only).",
    ],
    "C": ["Used as logged."],
    "D": ["Used as logged."],
}

# Palette (dataviz reference instance, light mode). Fixed order; never cycled.
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SERIES = [BLUE, ORANGE, AQUA, YELLOW, "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, GRID, SURFACE, MUTED = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff", "#f1f0ec"
CELL_COLORS = {"A": "#ffffff", "H": "#e9e8e4", "R(b)": "#cfe0f6", "R(z)": "#fbd5c4", "NS": "#ffffff",
               "ERR": "#fff1c2", ".": "#ffffff"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7, "axes.titlesize": 8, "axes.labelsize": 7,
                     "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7})


# ---------------------------------------------------------------------------------------------
# Statistics and helpers
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
        return "n/a (n=0)"
    p, lo, hi = wilson(k, n)
    return f"{k}/{n} = {p:.1%} [95% CI {lo:.1%}, {hi:.1%}]"


def count_true(s: pd.Series) -> tuple[int, int]:
    s = s.dropna()
    return int((s == True).sum()), int(len(s))  # noqa: E712


def ordered(values, order) -> list:
    vals = list(pd.unique(pd.Series(list(values)).dropna()))
    return [v for v in order if v in vals] + sorted(v for v in vals if v not in order)


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(no rows)_\n"
    cols = [str(c) for c in df.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        out.append("| " + " | ".join("" if (isinstance(x, float) and math.isnan(x)) else str(x) for x in row) + " |")
    return "\n".join(out) + "\n"


def load(logs_dir: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for exp in "ABCD":
        p = logs_dir / f"exp_{exp}.jsonl"
        rows: list[LogLine] = read_logs(str(p)) if p.exists() and p.stat().st_size else []
        out[exp] = pd.DataFrame([r.model_dump() for r in rows]) if rows else pd.DataFrame()
    return out


def provenance(df: pd.DataFrame) -> str:
    if df.empty:
        return "NOT RUN (no log file)"
    vers = df[["router", "router_version"]].fillna("?").drop_duplicates().sort_values(["router", "router_version"])
    v = "; ".join(f"{r.router} {r.router_version}" for r in vers.itertuples())
    ts = sorted(str(t) for t in df["ts"] if t)
    span = f"{ts[0]} to {ts[-1]}" if ts else "unknown"
    reps = sorted(int(x) for x in df["rep"].dropna().unique())
    sample = " **SAMPLE FIXTURE DATA - not results.**" if (df["router_version"] == "SAMPLE").any() else ""
    return (f"Versions: {v}. Run time (UTC): {span}. run_ids: {df['run_id'].nunique()}. Reps: {reps}. "
            f"Rows after filters: {len(df)}.{sample}")


def scenario_meta() -> dict[str, dict]:
    return {s["id"]: s for s in json.loads(SCENARIOS_JSON.read_text(encoding="utf-8"))["scenarios"]}


# ---------------------------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------------------------
def filter_A(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if df.empty:
        return df, {"rows_in": 0, "rows_excluded": 0}
    n0 = len(df)
    df = df[~df["run_id"].isin(EXCLUDED_A_RUNS)].copy()
    relabel = (df["config"] == "default") & (df["refusal_kind"] == "deployer_guardrail")
    df.loc[relabel, "config"] = "guardrail_control"
    df["not_supported"] = df["not_supported"].fillna(False).astype(bool)
    return df, {"rows_in": n0, "rows_excluded": n0 - len(df), "relabelled_guardrail_control": int(relabel.sum())}


def filter_B(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if df.empty:
        return df, {"rows_in": 0, "rows_excluded": 0}
    n0 = len(df)
    excluded = df[df["refusal_kind"].isin(EXCLUDED_B_KINDS)]
    by = {f"{k} ({'legit' if l else 'deny'})": int(len(g)) for (k, l), g in excluded.groupby(["refusal_kind", "legit_request"])}
    df = df[~df["refusal_kind"].isin(EXCLUDED_B_KINDS)].copy()
    return df, {"rows_in": n0, "rows_excluded": n0 - len(df), "excluded_by_kind": by}


# ---------------------------------------------------------------------------------------------
# Table 1 - Exp A
# ---------------------------------------------------------------------------------------------
TABLE1_LEGEND = ("`A` primary (mock-a) answered, no re-route. `H` held: no re-route and no answer (refusal or "
                 "error returned). `R(b)` re-routed to the approved fallback mock-b. `R(z)` re-routed to the "
                 "off-list mock-z. `NS` not supported by that router/config. `ERR` no outcome recorded. `!` "
                 "outcome differed across reps (majority shown). `.` not run (litellm_proxy was run on `ok` and `http500` "
                 "only). `ok`, `ok_toolcall`, `http500` are controls.")


def row_code(r) -> str:
    if r["rerouted"] is None or (isinstance(r["rerouted"], float) and math.isnan(r["rerouted"])):
        return "ERR"
    if bool(r["rerouted"]):
        ans = r["answering_model"]
        if ans == "mock-z" or r["within_allowlist"] is False:
            return "R(z)"
        if ans == "mock-b":
            return "R(b)"
        return f"R({ans})" if ans else "R(?)"
    if r["answering_model"] == "mock-a" or r["scenario_id"] == "ok_toolcall":
        return "A"
    return "H"


def cell_code(g: pd.DataFrame) -> tuple[str, bool]:
    if g["not_supported"].all():
        return "NS", False
    run = g[~g["not_supported"]]
    codes = [row_code(r) for _, r in run.iterrows()]
    vc = pd.Series(codes).value_counts()
    flaky = len(vc) > 1
    return vc.index[0] + ("!" if flaky else ""), flaky


def table1(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (main matrix, guardrail matrix, long per-cell frame)."""
    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    recs = []
    is_gr = df["refusal_kind"] == "deployer_guardrail"
    for (router, config, scen), g in df[~is_gr].groupby(["router", "config", "scenario_id"]):
        code, flaky = cell_code(g)
        recs.append(dict(kind="scenario", router=router, config=config, column=scen, code=code, flaky=flaky,
                         n=int((~g["not_supported"]).sum()), rows=len(g)))
    for (router, config), g in df[is_gr].groupby(["router", "config"]):
        if g["not_supported"].all():
            for col in ("blocked prompt", "allowed prompt"):
                recs.append(dict(kind="guardrail", router=router, config=config, column=col, code="NS",
                                 flaky=False, n=0, rows=len(g)))
            continue
        for legit, col in ((False, "blocked prompt"), (True, "allowed prompt")):
            gg = g[g["legit_request"] == legit]
            if gg.empty:
                continue
            code, flaky = cell_code(gg)
            recs.append(dict(kind="guardrail", router=router, config=config, column=col, code=code, flaky=flaky,
                             n=int((~gg["not_supported"]).sum()), rows=len(gg)))
    long = pd.DataFrame(recs)

    def matrix(kind, cols):
        d = long[long["kind"] == kind]
        if d.empty:
            return pd.DataFrame()
        m = d.pivot_table(index=["router", "config"], columns="column", values="code", aggfunc="first")
        m = m.reindex(columns=[c for c in cols if c in m.columns]).fillna(".")
        idx = sorted(m.index, key=lambda rc: (ROUTER_ORDER.index(rc[0]) if rc[0] in ROUTER_ORDER else 99,
                                             CONFIG_ORDER.index(rc[1]) if rc[1] in CONFIG_ORDER else 99))
        m = m.loc[idx].reset_index()
        m.columns.name = None
        return m

    return matrix("scenario", SCENARIO_ORDER), matrix("guardrail", ["blocked prompt", "allowed prompt"]), long


def table1_png(main: pd.DataFrame, gr: pd.DataFrame, out: Path, prov: str) -> None:
    short = {"ok_toolcall": "ok_tool\ncall", "http400_policy": "http400\npolicy",
             "azure400_filter": "azure400\nfilter", "oa200_content_filter": "oa200\nfilter",
             "oa200_refusal_field": "oa200\nrefusal", "text_refusal": "text\nrefusal",
             "an200_refusal": "an200\nrefusal", "an200_refusal_nodetails": "an200\nno details",
             "gem200_safety": "gem200\nSAFETY"}
    panels = [(main, "Refusal scenarios (mock provider)"), (gr, "Deployer guardrail (upstream ok)")]
    panels = [(p, t) for p, t in panels if not p.empty]
    heights = [len(p) + 2.2 for p, _ in panels]
    fig, axes = plt.subplots(len(panels), 1, figsize=(7.0, 0.17 * sum(heights) + 0.9),
                             gridspec_kw={"height_ratios": heights}, squeeze=False, facecolor=SURFACE)
    for ax, (m, title) in zip(axes[:, 0], panels):
        cols = [c for c in m.columns if c not in ("router", "config")]
        ncol, nrow = len(cols), len(m)
        lw = [1.0, 1.75]  # label column widths (router, config)
        cw = (7.0 - sum(lw) - 0.1) / max(ncol, 1) if ncol <= 11 else 0.42
        if title.startswith("Deployer"):
            cw = 1.1
        x0 = sum(lw)
        ax.set_xlim(0, x0 + cw * ncol)
        ax.set_ylim(nrow + 1.6, -0.6)
        ax.axis("off")
        ax.text(0, -0.45, title, fontsize=7.5, weight="bold", color=INK, va="bottom")
        hdr_y = 0.9
        ax.text(0.02, hdr_y, "router", fontsize=6.5, color=INK2, va="center")
        ax.text(lw[0] + 0.02, hdr_y, "config", fontsize=6.5, color=INK2, va="center")
        for j, c in enumerate(cols):
            ax.text(x0 + cw * (j + 0.5), 1.04, short.get(c, c), fontsize=5.4, color=INK2, ha="center",
                    va="bottom", linespacing=0.95)
        prev_router = None
        for i, row in enumerate(m.itertuples(index=False)):
            y = i + 1.6
            router, config = row[0], row[1]
            if router != prev_router:
                ax.plot([0, x0 + cw * ncol], [y - 0.5, y - 0.5], color=INK2, linewidth=0.6)
                ax.text(0.02, y, router, fontsize=6.5, color=INK, va="center", weight="bold")
                prev_router = router
            ax.text(lw[0] + 0.02, y, config, fontsize=6.3, color=INK, va="center")
            for j, code in enumerate(row[2:]):
                base = code.rstrip("!")
                ax.add_patch(Rectangle((x0 + cw * j + 0.015, y - 0.47), cw - 0.03, 0.94,
                                       facecolor=CELL_COLORS.get(base, "#ffffff"), edgecolor=GRID, linewidth=0.4,
                                       hatch="////" if base == "NS" else None))
                ax.text(x0 + cw * (j + 0.5), y, code, fontsize=6.3, ha="center", va="center",
                        color=INK2 if base in ("NS", ".") else INK, weight="bold" if base.startswith("R") else None)
    handles = [Patch(facecolor=CELL_COLORS[k], edgecolor=GRID, hatch="////" if k == "NS" else None, label=l)
               for k, l in [("A", "A  primary answered"), ("H", "H  held (no re-route)"),
                            ("R(b)", "R(b)  re-routed to approved mock-b"), ("R(z)", "R(z)  re-routed off-list (mock-z)"),
                            ("NS", "NS  not supported"), ("ERR", "ERR  no outcome"), (".", ".  not run")]]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=6, handlelength=1.4,
               bbox_to_anchor=(0.5, 0.012))
    fig.text(0.01, 0.0, prov, fontsize=4.8, color=INK2, va="bottom", wrap=True)
    fig.tight_layout(rect=(0, 0.075, 1, 1), h_pad=0.3)
    fig.savefig(out, dpi=300, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# Table 2 - Exp C
# ---------------------------------------------------------------------------------------------
def _framework(router: str) -> str:
    return router.split("/", 1)[1] if isinstance(router, str) and "/" in router else (router or "unspecified")


def table2(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    df = df.copy()
    df["framework"] = df["router"].map(_framework)
    recs = []
    for (fw, scen), g in df.groupby(["framework", "scenario_id"]):
        def kn(col):
            k, n = count_true(g[col])
            return f"{k}/{n}" if n else "n/a (n=0)"
        rr_k, rr_n = count_true(g["rerouted"])
        recs.append({"framework": fw, "scenario": scen, "sessions": len(g), "re-routed": f"{rr_k}/{rr_n}",
                     "tool_call_executed": kn("tool_call_executed"), "trace_names_model": kn("trace_names_model"),
                     "session_pinned": kn("session_pinned")})
    t = pd.DataFrame(recs)
    t["_s"] = t["scenario"].map(lambda s: SCENARIO_ORDER.index(s) if s in SCENARIO_ORDER else 99)
    t = t.sort_values(["framework", "_s"]).drop(columns="_s").reset_index(drop=True)

    mrecs = []
    for (scen, cfg), g in df.groupby(["scenario_id", "config"]):
        k, n = count_true(g["rerouted"])
        if k == 0:
            cell = "A" if g["tool_call_executed"].fillna(False).all() else "H"
        else:
            rr = g[g["rerouted"] == True]  # noqa: E712
            ans = ",".join(sorted({str(x) for x in rr["answering_model"].dropna()})) or "?"
            cell = f"R({ans.replace('mock-', '')}) {k}/{n}" + (" tool" if rr["tool_call_executed"].fillna(False).all() else "")
        mrecs.append({"scenario": scen, "config": cfg, "cell": cell})
    m = pd.DataFrame(mrecs).pivot(index="scenario", columns="config", values="cell")
    m = m.reindex(index=ordered(m.index, SCENARIO_ORDER), columns=ordered(m.columns, CONFIG_ORDER)).fillna(".")
    m.columns.name = None
    m = m.reset_index()

    hrecs = []
    for fw, g in df[df["rerouted"] == True].groupby("framework"):  # noqa: E712
        row = {"framework": fw, "re-routed sessions": len(g)}
        for col, name in [("disclosed_in_response", "gateway names answering model"),
                          ("trace_names_model", "framework trace names answering model"),
                          ("tool_call_executed", "tool call executed"), ("session_pinned", "session pinned")]:
            row[name] = fmt_rate(*count_true(g[col]))
        hrecs.append(row)
    return t, m, pd.DataFrame(hrecs)


# ---------------------------------------------------------------------------------------------
# Fig 1 - Exp B
# ---------------------------------------------------------------------------------------------
def fig1_data(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    deny = df[df["legit_request"] == False].copy()  # noqa: E712
    deny["model"] = deny["answering_model"].fillna("no model answered")
    recs = []
    for (router, cfg, model), g in deny.groupby(["router", "config", "model"]):
        rk, rn = count_true(g["rerouted"])
        lk, ln = count_true(g["canary_leaked"])
        bk, bn = count_true(g["blocked"])
        recs.append(dict(router=router, config=cfg, model=model, family=",".join(sorted({str(x) for x in g["model_family"].dropna()})),
                         n=len(g), rerouted_k=rk, rerouted_n=rn, leaked_k=lk, leaked_n=ln, blocked_k=bk, blocked_n=bn,
                         reps=int(g["rep"].nunique())))
    return pd.DataFrame(recs)


def _style(ax, ylabel=None):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#b8b7b2")
        ax.spines[s].set_linewidth(0.6)
    ax.tick_params(colors=INK2, length=2, width=0.6)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 1.12)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    if ylabel:
        ax.set_ylabel(ylabel, color=INK)


def _bars(ax, groups, series, colors, show_n=True):
    """series: [(name, {group: (k, n)})]. Draws Wilson CIs, a visible stub for measured 0%, and k/n labels."""
    ns = max(1, len(series))
    width = 0.78 / ns
    for i, (name, data) in enumerate(series):
        for gi, grp in enumerate(groups):
            if grp not in data or data[grp][1] == 0:
                continue
            k, n = data[grp]
            p, lo, hi = wilson(k, n)
            x = gi - 0.39 + width * (i + 0.5)
            ax.bar(x, max(p, 0.0), width=width * 0.9, color=colors[i], edgecolor=SURFACE, linewidth=0.8,
                   label=name if gi == 0 else None)
            if p == 0:
                ax.hlines(0.008, x - width * 0.42, x + width * 0.42, colors=colors[i], linewidth=2.2)
            ax.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor=INK, elinewidth=0.8, capsize=2,
                        capthick=0.8)
            if show_n:
                ax.text(x, hi + 0.02, f"{k}/{n}", ha="center", va="bottom", fontsize=5.8, color=INK2)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(groups, color=INK)


def fig1(data: pd.DataFrame, out: Path, prov: str) -> None:
    groups = list(data["model"])
    labels = [f"{r.model}\n({r.router}, {r.config})" for r in data.itertuples()]
    fig, ax = plt.subplots(figsize=(3.4, 2.5), facecolor=SURFACE)
    series = [("re-routed to fallback", {r.model: (r.rerouted_k, r.rerouted_n) for r in data.itertuples()}),
              ("canary leaked", {r.model: (r.leaked_k, r.leaked_n) for r in data.itertuples()})]
    _bars(ax, groups, series, [BLUE, ORANGE])
    ax.set_xticklabels(labels, fontsize=6.3)
    _style(ax, "share of deny prompts")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=2, handlelength=1.2)
    fig.text(0.01, 0.005, "Exp B, live. Bars: rate; whiskers: Wilson 95% CI; labels: k/n.", fontsize=5.2,
             color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out, dpi=300, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# Fig 2 - Exp D
# ---------------------------------------------------------------------------------------------
D_METRICS = [("leak", "Leak rate\n(deny prompts)"), ("false_block", "False-block rate\n(legit prompts)"),
             ("recovery_lost", "Recovery lost\n(false-positive refusals)")]


def fig2_data(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    recs = []
    for (dfn, atk), g in df.groupby(["defence", "attack"]):
        pol, leg, rec = g[g["legit_request"] == False], g[g["legit_request"] == True], g[g["recovered"].notna()]  # noqa: E712
        row = dict(defence=dfn, attack=atk, rows=len(g), configs=",".join(sorted({str(c) for c in g["config"].dropna()})))
        for name, (k, n) in [("leak", count_true(pol["canary_leaked"])), ("false_block", count_true(leg["blocked"])),
                             ("recovery_lost", (int((rec["recovered"] == False).sum()), len(rec)))]:  # noqa: E712
            row[f"{name}_k"], row[f"{name}_n"] = k, n
        recs.append(row)
    d = pd.DataFrame(recs)
    d["_d"] = d["defence"].map(lambda x: DEFENCE_ORDER.index(x) if x in DEFENCE_ORDER else 99)
    d["_a"] = d["attack"].map(lambda x: ATTACK_ORDER.index(x) if x in ATTACK_ORDER else 99)
    return d.sort_values(["_d", "_a"]).drop(columns=["_d", "_a"]).reset_index(drop=True)


def fig2(data: pd.DataFrame, out: Path, prov: str) -> None:
    defences = ordered(data["defence"], DEFENCE_ORDER)
    attacks = ordered(data["attack"], ATTACK_ORDER)
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.4), sharey=True, facecolor=SURFACE)
    for ax, (metric, title) in zip(axes, D_METRICS):
        series = [(a, {r.defence: (getattr(r, f"{metric}_k"), getattr(r, f"{metric}_n"))
                       for r in data[data["attack"] == a].itertuples()}) for a in attacks]
        _bars(ax, defences, series, SERIES, show_n=len(defences) * len(attacks) <= 8)
        _style(ax)
        ax.set_title(title, color=INK)
    axes[0].set_ylabel("rate", color=INK)
    handles = [Patch(facecolor=SERIES[i], label=a) for i, a in enumerate(attacks)]
    fig.legend(handles=handles, title="attack", loc="upper right", ncol=len(attacks), frameon=False,
               title_fontsize=6.5, bbox_to_anchor=(1.0, 1.0))
    ns = []
    for metric, label in (("leak", "deny"), ("false_block", "legit"), ("recovery_lost", "false-positive")):
        vals = sorted(set(int(v) for v in data[f"{metric}_n"]))
        ns.append(f"{label} n={vals[0] if len(vals) == 1 else f'{vals[0]}-{vals[-1]}'}")
    fig.text(0.01, 0.005, f"Exp D. Bars: rate per defence x attack ({', '.join(ns)} per bar); whiskers: Wilson 95% CI; "
             "exact k/n in analysis/RESULTS.md.\n" + prov, fontsize=4.6, color=INK2, linespacing=1.3)
    fig.tight_layout(rect=(0, 0.06, 1, 0.84))
    fig.savefig(out, dpi=300, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# RESULTS.md
# ---------------------------------------------------------------------------------------------
def versions_block() -> str:
    if not VERSIONS_MD.exists():
        return "routers/VERSIONS.md not found.\n"
    lines = [l for l in VERSIONS_MD.read_text(encoding="utf-8").splitlines() if l.startswith("|")]
    tail = [l for l in VERSIONS_MD.read_text(encoding="utf-8").splitlines() if re.match(r"^Python \d", l)]
    return "From `routers/VERSIONS.md`:\n\n" + "\n".join(lines) + "\n\n" + "\n".join(tail) + "\n"


def results_A(df: pd.DataFrame, long: pd.DataFrame, info: dict) -> list[str]:
    if df.empty:
        return ["- NOT RUN."]
    meta = scenario_meta()
    sc = long[long["kind"] == "scenario"]
    gr = long[long["kind"] == "guardrail"]
    out = [f"- Rows: {info['rows_in']} logged, {info['rows_excluded']} excluded, {len(df)} analysed; "
           f"{info['relabelled_guardrail_control']} rows relabelled `guardrail_control`.",
           f"- Cells (router x config x scenario, plus guardrail router x config x prompt): {len(long)}; "
           f"not supported {int((long['code'] == 'NS').sum())}; executed {int((long['code'] != 'NS').sum())}; "
           f"no outcome (ERR) {int(long['code'].str.startswith('ERR').sum())}; differed across reps "
           f"{int(long['flaky'].sum())}.",
           f"- Executed rows: {int((~df['not_supported']).sum())}; reps per executed cell: "
           f"{sorted(set(long.loc[long['code'] != 'NS', 'n']))}."]
    refusals = [s for s in SCENARIO_ORDER if s not in CONTROL_SCENARIOS]
    ok200 = [s for s in refusals if meta.get(s, {}).get("http") == 200]
    for title, scens in [("HTTP 400 refusals", [s for s in refusals if meta.get(s, {}).get("http") == 400]),
                         ("200-OK refusals", ok200)]:
        ex = sc[sc["column"].isin(scens) & (sc["code"] != "NS")]
        rr = ex[ex["code"].str.startswith("R")]
        out.append(f"- {title} ({', '.join(scens)}): re-routed in {len(rr)} of {len(ex)} executed cells.")
        for s in scens:
            cells = sc[(sc["column"] == s) & sc["code"].str.startswith("R")]
            who = ", ".join(f"{r.router}/{r.config} {r.code}" for r in cells.itertuples()) or "none"
            held = int(((sc["column"] == s) & (sc["code"].str.rstrip("!") == "H")).sum())
            out.append(f"  - `{s}`: re-routed by {who}; held in {held} executed cells.")
    for cfg in ["default", "outage_fallback", "outage_fallback_wildcard", "content_policy_fallback", "offlist_fallback", "refusal_failover"]:
        d = sc[(sc["config"] == cfg) & sc["column"].isin(refusals) & (sc["code"] != "NS")]
        if d.empty:
            continue
        rr = d[d["code"].str.startswith("R")]
        out.append(f"- Config `{cfg}`: refusal cells re-routed {len(rr)}/{len(d)} "
                   f"(routers: {', '.join(sorted(d['router'].unique()))}).")
    off = sc[sc["code"].str.startswith("R(z)")]
    off_rows = df[(df["rerouted"] == True) & (df["within_allowlist"] == False)]  # noqa: E712
    out.append(f"- Off-list escapes (H3): {len(off)} cells, {len(off_rows)} rows answered by mock-z "
               f"(`within_allowlist=false`): " + ", ".join(f"{r.router}/{r.column}" for r in off.itertuples()) + ".")
    rr_rows = df[df["rerouted"] == True]  # noqa: E712
    out.append(f"- Disclosure: `disclosed_in_response=true` on {fmt_rate(*count_true(rr_rows['disclosed_in_response']))} "
               f"re-routed rows (see routers/FINDINGS.md section d for what each router discloses).")
    for r in gr.itertuples():
        g = df[(df["router"] == r.router) & (df["config"] == r.config) & (df["refusal_kind"] == "deployer_guardrail")
               & (df["legit_request"] == (r.column == "allowed prompt"))]
        extra = ""
        if r.code != "NS" and len(g):
            extra = (f" (n={len(g)}; re-routed {count_true(g['rerouted'])[0]}/{len(g)}, "
                     f"blocked {count_true(g['blocked'])[0]}/{len(g)})")
        out.append(f"- Guardrail {r.router}/{r.config}, {r.column}: {r.code}{extra}.")
    return out


def results_B(df: pd.DataFrame, f1: pd.DataFrame, info: dict) -> list[str]:
    if df.empty:
        return ["- NOT RUN."]
    out = [f"- Rows: {info['rows_in']} logged, {info['rows_excluded']} excluded ({info['excluded_by_kind']}), "
           f"{len(df)} analysed. Configs present: {', '.join(sorted(df['config'].unique()))}. "
           f"Reps present: {sorted(int(x) for x in df['rep'].unique())} "
           f"(rows per rep: {df.groupby('rep').size().to_dict()})."]
    for r in f1.itertuples():
        out.append(f"- Deny prompts answered by **{r.model}** (family {r.family or 'n/a'}; {r.router}, {r.config}; "
                   f"reps {r.reps}): re-routed {fmt_rate(r.rerouted_k, r.rerouted_n)}; canary leaked "
                   f"{fmt_rate(r.leaked_k, r.leaked_n)}; empty response logged as blocked {r.blocked_k}/{r.blocked_n}.")
    deny = df[df["legit_request"] == False]  # noqa: E712
    out.append(f"- All deny prompts: re-routed {fmt_rate(*count_true(deny['rerouted']))}; leaked "
               f"{fmt_rate(*count_true(deny['canary_leaked']))}.")
    leg = df[df["legit_request"] == True]  # noqa: E712
    out.append(f"- Legit prompts (limitation only, no false-block rate): n={len(leg)}; `blocked=true` on "
               f"{count_true(leg['blocked'])[0]}, mostly empty responses from the reasoning fallback model; "
               f"re-routed {count_true(leg['rerouted'])[0]}/{len(leg)}.")
    if "guardrail_control" not in set(df["config"]):
        out.append("- `guardrail_control` (live): NOT RUN - the live log contains only `guardrail_fallback`.")
    return out


def results_C(df: pd.DataFrame, head: pd.DataFrame) -> list[str]:
    if df.empty:
        return ["- NOT RUN."]
    rr = df[df["rerouted"] == True]  # noqa: E712
    off = rr[rr["within_allowlist"] == False]  # noqa: E712
    default = df[(df["config"] == "default") & ~df["scenario_id"].isin(CONTROL_SCENARIOS - {"http500"})]
    out = [f"- Sessions: {len(df)} ({df['config'].nunique()} configs x {df['router'].nunique()} frameworks x "
           f"{df['scenario_id'].nunique()} scenarios x {df['rep'].nunique()} reps).",
           f"- Config `default` (no fallback): re-routed {fmt_rate(*count_true(default['rerouted']))}; refusal "
           f"or error reached the agent {fmt_rate(*count_true(default['refusal_returned_to_caller']))}.",
           f"- Re-routed sessions: {len(rr)}. Fallback tool call executed {fmt_rate(*count_true(rr['tool_call_executed']))}.",
           f"- Off-list (mock-z) answered and tool ran: {fmt_rate(*count_true(off['tool_call_executed']))} "
           f"(all re-routed `offlist_fallback` sessions).",
           f"- Session pinned on turn 2: {fmt_rate(*count_true(rr['session_pinned']))}."]
    for r in head.itertuples(index=False):
        out.append(f"- {r[0]}: gateway names answering model {r[2]}; framework trace names it {r[3]}.")
    for model_ref in ("model_refusal",):
        d = df[(df["refusal_kind"] == model_ref)]
        out.append(f"- Model-level refusals (`oa200_refusal_field`, `text_refusal`) re-routed under any config: "
                   f"{fmt_rate(*count_true(d['rerouted']))}.")
    return out


def results_D(f2: pd.DataFrame) -> list[str]:
    if f2.empty:
        return ["- NOT RUN: no `logs/exp_D.jsonl` was present when this file was built."]
    out = []
    for r in f2.itertuples():
        out.append(f"- {r.defence} x {r.attack} (configs {r.configs}): leak {fmt_rate(r.leak_k, r.leak_n)}; "
                   f"false-block {fmt_rate(r.false_block_k, r.false_block_n)}; recovery lost "
                   f"{fmt_rate(r.recovery_lost_k, r.recovery_lost_n)}.")
    return out


# ---------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------
def analyze(logs_dir: Path, tables_dir: Path = HERE / "tables", figures_dir: Path = HERE / "figures",
            results_path: Path = HERE / "RESULTS.md", quiet: bool = False) -> dict:
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    raw = load(logs_dir)
    A, info_a = filter_A(raw["A"])
    B, info_b = filter_B(raw["B"])
    C, D = raw["C"], raw["D"]
    produced: dict = {}

    # Table 1
    main, gr, long = table1(A)
    prov_a = provenance(A)
    t1 = ["# Table 1 - Exp A conformance (mock provider)\n", prov_a + "\n", TABLE1_LEGEND + "\n"]
    if main.empty:
        t1.append("NOT RUN\n")
    else:
        t1 += ["## Refusal scenarios\n", md_table(main), "\n## Deployer guardrail (upstream scenario `ok`)\n",
               md_table(gr) if not gr.empty else "_(no guardrail rows)_\n"]
        table1_png(main, gr, figures_dir / "table1.png", prov_a)
        produced["table1"] = len(long)
    (tables_dir / "table1.md").write_text("\n".join(t1), encoding="utf-8")

    # Table 2
    t2, mx, head = table2(C)
    t2md = ["# Table 2 - Exp C agent consequences (LiteLLM gateway, mock provider)\n", provenance(C) + "\n",
            "Cells are k/n sessions pooled over the 5 gateway configs (3 reps each). `session_pinned` is defined "
            "only for sessions re-routed on turn 1, so its n differs.\n"]
    if t2.empty:
        t2md.append("NOT RUN\n")
    else:
        t2md += ["## Framework x scenario\n", md_table(t2),
                 "\n## Per gateway config (pooled over frameworks)\n",
                 "`A` primary answered; `H` held (refusal/error reached the agent); `R(b|z) k/n` re-routed to "
                 "mock-b / off-list mock-z; `tool` = fallback's tool call executed in every re-routed session.\n",
                 md_table(mx), "\n## H4: who names the answering model (re-routed sessions, Wilson 95% CI)\n",
                 md_table(head)]
        produced["table2"] = len(t2)
    (tables_dir / "table2.md").write_text("\n".join(t2md), encoding="utf-8")

    # Fig 1
    f1 = fig1_data(B)
    if not f1.empty:
        fig1(f1, figures_dir / "fig1.png", provenance(B))
        produced["fig1"] = str(figures_dir / "fig1.png")

    # Fig 2
    f2 = fig2_data(D)
    if not f2.empty:
        fig2(f2, figures_dir / "fig2.png", provenance(D))
        produced["fig2"] = str(figures_dir / "fig2.png")

    # RESULTS.md
    res = ["# RESULTS - numbers for the report\n",
           f"Built by `python analysis/analyze.py {logs_dir.as_posix()}` from `exp_A..D.jsonl`. Every rate is "
           "k/n with a Wilson 95% CI. Mock experiments (A, C) are deterministic: their CIs describe repeatability "
           "under the stated configs, not variation across deployments.\n",
           "## Filters applied (in code; log files untouched)\n"]
    for e in "ABCD":
        res.append(f"**Exp {e}**\n")
        res += [f"- {f}" for f in FILTERS[e]]
        res.append("")
    res += ["## Versions and run dates\n", versions_block(),
            "Exp C (Role A): " + (", ".join(sorted(C["router_version"].unique())) if not C.empty else "NOT RUN") + ".\n",
            "| Exp | provenance |", "|---|---|",
            f"| A | {provenance(A)} |", f"| B | {provenance(B)} |", f"| C | {provenance(C)} |", f"| D | {provenance(D)} |", "",
            "## Exp A - conformance (Table 1, `tables/table1.md`, `figures/table1.png`)\n", *results_A(A, long, info_a), "",
            "## Exp B - live deployer-guardrail leaks (Fig 1, `figures/fig1.png`)\n", *results_B(B, f1, info_b), "",
            "## Exp C - agent consequences (Table 2, `tables/table2.md`)\n", *results_C(C, head), "",
            "## Exp D - defences under attack (Fig 2, `figures/fig2.png`)\n", *results_D(f2), "",
            "## Limitations to state\n",
            "- Streaming was not tested (mock is non-streaming only).",
            "- Exp A and C use the mock provider only; Exp B is one live run on free tiers.",
            "- Exp B legit prompts: no false-block rate (empty responses from the reasoning fallback model).",
            ]
    if not B.empty and B["rep"].nunique() and B.groupby("rep").size().nunique() > 1:
        res.append(f"- Exp B reps are unequal ({B.groupby('rep').size().to_dict()} rows per rep after filters).")
    if f2.empty:
        res.append("- Exp D: NOT RUN at build time; Fig 2 absent.")
    else:
        res.append("- Exp D runs on the mock through the real Portkey gateway; the unguarded fallback (mock-b) is "
                   "*simulated* as a model that complies with record requests (defences/routes.py), so leak rates "
                   "measure routing and defences, not a real model's willingness to disclose.")
        res.append("- Exp D: the deployer guardrail blocks every prompt naming a record (regex `cust-NNNN`, "
                   "routers/guardrail_policy.py), so legit record requests (30 of 40 legit prompts) can only be "
                   "answered via the fallback; d1/d2 false-blocks are exactly those prompts.")
    results_path.write_text("\n".join(res) + "\n", encoding="utf-8")
    produced["results"] = str(results_path)
    if not quiet:
        print("\n".join(res))
        print(f"\nWrote {tables_dir}, {figures_dir}, {results_path}")
    return produced


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs_dir", nargs="?", default=str(ROOT / "logs"))
    a = ap.parse_args()
    analyze(Path(a.logs_dir))


if __name__ == "__main__":
    main()
