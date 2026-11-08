# Routers status (Role B)

Router matrix below was checked 2026-11-08 against the full mock, 1 rep. Experiment A itself is NOT RUN.

| Adapter | Configs | Styles |
|---|---|---|
| litellm 1.108.3 | default, outage_fallback, outage_fallback_wildcard, content_policy_fallback, offlist_fallback | openai, anthropic, gemini |
| langchain-core 1.7.6 | default, outage_fallback, refusal_failover (openai style only), offlist_fallback | openai, anthropic |
| portkey 1.15.2 | default, outage_fallback, content_policy_fallback, offlist_fallback, guardrail_fallback, guardrail_control | openai, anthropic, gemini |

## Done
- `common.SCENARIO_STYLE` maps every scenario to a wire style; the runner passes it to `adapter.send()`.
- `supports_cell(config, scenario)` on every adapter; unsupported cells log `not_supported=True`.
- Anthropic and Gemini paths use each router's own custom-base-URL option.
- Selftest covers the style mapping, `supports_cell` and the runner passing the style.
- Live check: an200_refusal, an200_refusal_nodetails, gem200_safety under default and outage_fallback: no re-route, refusal returned.
- Control: http500 under outage_fallback reaches mock-b in every supported non-openai style, so fallback targets work.

## UNVERIFIED
- langchain gemini: needs langchain-google-genai, not installed and not on the PLAN.md 8.6 list.
- refusal_failover on litellm and portkey: no confirmed setting.
- `npx -y @portkey-ai/gateway@1.15.2` exited 1 with no output on this run; cause not found. Direct `node <npx cache>/.../build/start-server.js` with the same preload worked.

## Next
1. Run Exp A with `AVAILABLE_SCENARIOS=*` (the runner's default still filters to 3 scenarios).
2. LiteLLM `guardrail_fallback` (Phase 2).
3. Exp B in `live/`.
4. Add Bifrost and atomic if time allows.
