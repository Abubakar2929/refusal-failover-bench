# Routers status (Role B)

Experiment A: full matrix RUN 2026-11-08, 3 reps, 11 scenarios, mock provider only. Result: `logs/exp_A.jsonl` (630 lines, `run_id` 52919b8c79a14f9d88b5ac410d30c527). Table and findings: `routers/FINDINGS.md`. Portkey start/stop: `routers/HOWTO_PORTKEY.md`.

| Adapter | Configs | Styles |
|---|---|---|
| litellm 1.108.3 | default, outage_fallback, outage_fallback_wildcard, content_policy_fallback, offlist_fallback | openai, anthropic, gemini |
| langchain-core 1.7.6 | default, outage_fallback, refusal_failover (openai style only), offlist_fallback | openai, anthropic |
| portkey 1.15.2 | default, outage_fallback, content_policy_fallback, offlist_fallback, guardrail_fallback, guardrail_control | openai, anthropic, gemini |

## Exp A totals
210 cells: 69 not_supported, 141 executed, 0 flaky, 1 with no result.

## Done
- `common.SCENARIO_STYLE` maps every scenario to a wire style; the runner passes it to `adapter.send()`.
- `supports_cell(config, scenario)` on every adapter; unsupported cells log `not_supported=True`.
- Anthropic and Gemini paths use each router's own custom-base-URL option.
- Selftest covers the style mapping, `supports_cell` and the runner passing the style.
- Exp A full matrix, disclosure check and LiteLLM content-policy mapping, written up in `FINDINGS.md`.

## Known issues
- langchain / refusal_failover / ok_toolcall: `AttributeError: 'NoneType' object has no attribute 'text'` in the adapter on all 3 reps; outcome fields are null. Not fixed: the run did not crash.
- `ok_toolcall` lines log `answering_model: null` and `refusal_returned_to_caller: true` although mock-a answered with a tool call. Analysis must not count them as refusals.

## UNVERIFIED
- langchain gemini: needs langchain-google-genai, not installed and not on the PLAN.md 8.6 list.
- refusal_failover on litellm and portkey: no confirmed setting.
- `npx -y @portkey-ai/gateway@1.15.2` exits 1 with no output on this machine; cause not found. Direct `node` on the cached `start-server.js` with the same preload works.
- LiteLLM `azure/` deployment path: NOT RUN (the `azure400_filter` scenario went through the `openai/` provider).

## Next
1. LiteLLM `guardrail_fallback` (Phase 2).
2. Exp B in `live/`.
3. Add Bifrost and atomic if time allows.
