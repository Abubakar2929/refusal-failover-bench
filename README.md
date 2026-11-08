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
uvicorn contracts.fixtures.stub_provider:app --port 8900
python run.py --exp A --router litellm --config content_policy_fallback --scenario oa200_content_filter --reps 1
```

## Versions

| Component | Version | Installed by | Date |
|---|---|---|---|
| LiteLLM | | | |
| LangChain core | | | |
| Portkey gateway | | | |
| Bifrost | | | |
| atomic | | | |
| Agent framework (Exp C) | | | |
| Real models (Exp B) | | | |
