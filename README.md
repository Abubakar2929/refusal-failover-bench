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

## Setup

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python run.py --selftest
```

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
| Portkey gateway | | | |
| Bifrost | | | |
| atomic | | | |
| Agent framework (Exp C): openai-agents | 0.24.0 (openai SDK 3.46.0) | A | 2026-11-08 |
| Agent framework (Exp C): langgraph | 1.2.20 (langchain-core 1.7.6, langchain-openai 1.7.4) | A | 2026-11-08 |
| FastAPI / uvicorn / httpx (mock provider) | 0.162.2 / 0.54.0 / 0.28.1 | A | 2026-11-08 |
| pandas / scipy / matplotlib (analysis) | 3.1.1 / 1.18.1 / 3.11.2 | A | 2026-11-08 |
| Real models (Exp B) | | | |
