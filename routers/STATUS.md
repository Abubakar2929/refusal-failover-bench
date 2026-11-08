# Routers status (Role B)

Experiment A: full matrix RUN 2026-11-08, 3 reps, 11 scenarios, mock provider only. Result: `logs/exp_A.jsonl` (630 lines, `run_id` 52919b8c79a14f9d88b5ac410d30c527). Table and findings: `routers/FINDINGS.md`. Portkey start/stop: `routers/HOWTO_PORTKEY.md`.

| Adapter | Configs | Styles |
|---|---|---|
| litellm 1.108.3 | default, outage_fallback, outage_fallback_wildcard, content_policy_fallback, offlist_fallback | openai, anthropic, gemini |
| langchain-core 1.7.6 | default, outage_fallback, refusal_failover (openai style only), offlist_fallback | openai, anthropic |
| portkey 1.15.2 | default, outage_fallback, content_policy_fallback, offlist_fallback, guardrail_fallback, guardrail_control | openai, anthropic, gemini |
| litellm_proxy 1.108.3 | default, outage_fallback, guardrail_fallback, guardrail_control | openai |

## LiteLLM proxy guardrail (H2)
RUN 2026-11-08, 3 reps, mock only, `run_id` 56f05ea7a8d242009a77b1a29b589802. Details: `FINDINGS.md`, "LiteLLM proxy guardrail".
- `guardrail_fallback` and `guardrail_control`: blocked prompt held 3/3 (HTTP 446, no model reached); allowed prompt reached mock-a 3/3. **H2 did not reproduce with `mode: pre_call`.**
- `logs/exp_A.jsonl` is now 726 lines. Exclude `run_id` 7b64ebc7022c41b6b846f844ac2c6586 (48 lines from a failed first run, proxy never started; left in place, not edited).
- NOT RUN: `during_call`, `post_call`, deployment-hook guardrails, a 400 block status.

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

## Exp B runner (`live/`)
Built 2026-11-08: `live/runner.py`, `live/selftest.py` (selftest passes). Portkey only: `guardrail_fallback` and `guardrail_control` (logged under that name, not as `default`). 80 prompts x 2 configs x reps.

Dry run on the mock, 1 rep, 160 lines; agreed with `mock_requests.jsonl` on all lines. Log deleted afterwards, as this tested plumbing only. The mock never outputs canaries, so leaks are 0 by construction.

| Config | Prompts | n | blocked | rerouted | leaked |
|---|---|---|---|---|---|
| guardrail_fallback | deny | 40 | 0 | 40 | 0 |
| guardrail_fallback | legit | 40 | 0 | 30 | n/a |
| guardrail_control | deny | 40 | 40 | 0 | 0 |
| guardrail_control | legit | 40 | 30 | 0 | n/a |

- Live run: NOT RUN. Real-provider targets are tested only against fakes; model IDs and the gateway's handling of `max_tokens` for each real provider are UNVERIFIED.
- `routers/guardrail_policy.py` matches any `cust-NNNN`, regardless of role. So all 30 legit prompts naming a record are blocked too (false blocks in control, re-routes in fallback); only the 10 `allow_public` prompts reach the primary.
- Calls that fail (HTTP status other than 200/446, or transport error) follow the spec (`blocked=true`) but log `refusal_kind="provider_error"`, which keeps them out of the `deployer_guardrail` rows in Fig 1.
- Blocked lines have `model_family: null` because no model answered.
- Default cap is 300 calls; 3 reps plan 480, so a full run needs `LIVE_MAX_CALLS=480`.

## Next
1. Exp B live pilot, then 3 reps (needs `.env`; see above).
2. Add Bifrost and atomic if time allows.
