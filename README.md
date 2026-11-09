# refusal-failover-bench

Test suite and experiments measuring how LLM gateways and agent frameworks re-route model refusals (200-OK refusals, deployer guardrail blocks, models outside the approved list), with defences tested under attack. Built for the Apart Research Swarm Alignment Hackathon, Nov 2026.

See [PLAN.md](PLAN.md) for the build plan, roles and contracts.

## Builds on

- [failoverbench](https://github.com/failoverbench/failoverbench): licence decision: TBD (Role B)

## Hypotheses

- **H1:** Routers that re-route HTTP 400 refusals also re-route some 200-OK refusals when a refusal/content-policy fallback (or a LiteLLM wildcard `"*"` fallback) is configured; at least one framework does so by default (atomic).
- **H2:** At least one documented router setup re-routes a request blocked by the deployer's own guardrail.
- **H3:** Cross-provider fallback can leave an approved model list unless an explicit allowlist is enforced.
- **H4:** After a fallback, the answering model's identity is often missing from agent-framework traces even when the gateway reports it.
- **H5:** "Refusals are final" + allowlist stops leaks but loses false-positive recovery; a requester-bound permission check stops data leaks at lower cost.

![selftest](https://github.com/Abubakar2929/refusal-failover-bench/actions/workflows/selftest.yml/badge.svg)

## Reproduce

Everything below except Exp B runs on the local mock provider: no API keys, $0. Results are in
[analysis/RESULTS.md](analysis/RESULTS.md); tables in `analysis/tables/`, figures in `analysis/figures/`.

```bash
# 1. Environment (exact versions used for the logged runs)
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.lock
python run.py --selftest               # every module, offline, no keys

# 2. Rebuild every table and figure from the committed logs (one command)
python analysis/analyze.py logs/

# 3. Re-run the experiments (each appends to logs/exp_<X>.jsonl; delete the old file first for a clean run)
uvicorn mock_provider.app:app --host 127.0.0.1 --port 8900            # mock provider, terminal 1
NODE_OPTIONS=--require=./routers/configs/portkey_loopback.cjs \
  npx -y @portkey-ai/gateway@1.15.2 --port=8787 --headless            # Portkey, terminal 2 (see routers/HOWTO_PORTKEY.md)
python run.py --exp A --reps 3         # conformance matrix (mock; LiteLLM, LangChain, Portkey)
python run.py --exp C --reps 3         # agent consequences (starts its own LiteLLM proxies)
python run.py --exp D --reps 3         # defences under attack (mock + Portkey)
python run.py --exp B --reps 3         # live deployer-guardrail test: needs keys in .env, see routers/STATUS.md
python -m agent_exp.demo               # one 200-OK refusal re-routed live, shown three ways (for the video)
```

| Experiment | Log | Rows | Run date (UTC) |
|---|---|---|---|
| A conformance | `logs/exp_A.jsonl` | 726 (678 after the documented filter) | 2026-11-08 |
| B live guardrail | `logs/exp_B.jsonl` | 213 (171 after the documented filter) | 2026-11-08 |
| C agent consequences | `logs/exp_C.jsonl` (+ `exp_C_details.jsonl` evidence) | 300 | 2026-11-08 |
| D defences under attack | `logs/exp_D.jsonl` | 8400 | 2026-11-09 |

Windows: set `PYTHONUTF8=1` if a LiteLLM proxy exits at start-up with `UnicodeEncodeError`.

## Run

```bash
# Mock provider (all 11 scenarios; OpenAI, Anthropic and Gemini wire formats). Ground truth -> logs/mock_requests.jsonl
uvicorn mock_provider.app:app --port 8900

python run.py --exp A --router litellm --config content_policy_fallback --scenario oa200_content_filter --reps 1

# Exp C (agent consequences): starts the mock if needed and one LiteLLM proxy per config; $0, mock only
python run.py --exp C --reps 3
python run.py --exp C --router litellm/langgraph --config content_policy_fallback --scenario an200_refusal --reps 1

# All tables and figures from the logs (one command)
python analysis/analyze.py logs/
```

Mock provider notes (Role A):
- A refusal scenario is served only on its native API style (`mock_provider/formats.py: NATIVE_STYLES`); other styles get HTTP 404 `scenario_not_native_to_style`, so a mis-configured router can never silently test the wrong format.
- Streaming is not implemented: `stream: true` gets HTTP 400 `mock_streaming_not_supported` (stated limitation).
- Realism-only additions beyond `contracts/refusal_formats.md`: OpenAI `usage`, Gemini `usageMetadata` + `modelVersion` (LiteLLM 1.108.3 crashes with `KeyError('usageMetadata')` without it). Everything else is byte-for-byte the contract body; `mock_provider/selftest.py` enforces this.
- `ok_toolcall` returns a `write_record` tool call, then a final text answer once a tool result is in the conversation (so agent loops terminate).

## Versions

| Component | Version | Installed by | Date |
|---|---|---|---|
| Python | 3.12.3 | A | 2026-11-08 |
| LiteLLM (proxy, used as Exp C gateway) | 1.108.3 | A | 2026-11-08 |
| LangChain core | 1.7.6 (installed by A for Exp C; B to confirm for Exp A) | A | 2026-11-08 |
| Portkey gateway | 1.15.2 (see routers/VERSIONS.md) | B | 2026-11-08 |
| Bifrost | | | |
| atomic | | | |
| Agent framework (Exp C): openai-agents | 0.24.0 (openai SDK 3.46.0) | A | 2026-11-08 |
| Agent framework (Exp C): langgraph | 1.2.20 (langchain-core 1.7.6, langchain-openai 1.7.4) | A | 2026-11-08 |
| FastAPI / uvicorn / httpx (mock provider) | 0.162.2 / 0.54.0 / 0.28.1 | A | 2026-11-08 |
| pandas / scipy / matplotlib (analysis) | 3.1.1 / 1.18.1 / 3.11.2 | A | 2026-11-08 |
| Real models (Exp B) | | | |
