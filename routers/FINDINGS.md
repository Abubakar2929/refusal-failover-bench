# Experiment A findings (Role B)

Mock provider only; no real models. Non-streaming only. Source: `logs/exp_A.jsonl`.

## a) Versions and run

- Run date: 2026-11-08, 16:47:52Z to 16:49:11Z. `run_id` 52919b8c79a14f9d88b5ac410d30c527.
- Command: `AVAILABLE_SCENARIOS=* python run.py --exp A --reps 3`.
- litellm 1.108.3, langchain-core 1.7.6, langchain-openai 1.7.4, langchain-anthropic 1.7.10, openai (Python SDK) 3.46.0, @portkey-ai/gateway 1.15.2.
- Python 3.12.4, Node 22.22.0, Windows 11.
- Totals: 210 cells (630 log lines at 3 reps). 69 cells not supported (207 lines), 141 executed. 0 flaky. 1 cell with no result (3 lines).

## b) Conformance table

Legend:
- `R(b)` rerouted to mock-b. `R(z)` rerouted to off-list mock-z. `H` held: no re-route, and no answer returned. `NS` not supported. `!` outcome differed across the 3 reps (no such cell).
- Two codes added because the requested five cannot describe these cells:
  - `A`: primary mock-a answered, no re-route (the `ok` and `ok_toolcall` controls, and allowed guardrail prompts).
  - `ERR`: no outcome recorded.
- `H` on `http500` means the 500 error was returned without a re-route; that scenario is not a refusal.

| Router | Config | ok | ok_toolcall | http500 | http400_policy | azure400_filter | oa200_content_filter | oa200_refusal_field | text_refusal | an200_refusal | an200_refusal_nodetails | gem200_safety |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| litellm | default | A | A | H | H | H | H | H | H | H | H | H |
| litellm | outage_fallback | A | A | R(b) | R(b) | R(b) | H | H | H | H | H | H |
| litellm | outage_fallback_wildcard | A | A | R(b) | R(b) | R(b) | R(b) | H | H | R(b) | R(b) | R(b) |
| litellm | content_policy_fallback | A | A | H | H | H | R(b) | H | H | R(b) | R(b) | R(b) |
| litellm | offlist_fallback | A | A | R(z) | R(z) | R(z) | H | H | H | H | H | H |
| litellm | refusal_failover | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS |
| langchain | default | A | A | H | H | H | H | H | H | H | H | NS |
| langchain | outage_fallback | A | A | R(b) | R(b) | R(b) | H | H | H | H | H | NS |
| langchain | outage_fallback_wildcard | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS |
| langchain | content_policy_fallback | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS |
| langchain | offlist_fallback | A | A | R(z) | R(z) | R(z) | H | H | H | H | H | NS |
| langchain | refusal_failover | A | ERR | R(b) | R(b) | R(b) | R(b) | R(b) | H | NS | NS | NS |
| portkey | default | A | A | H | H | H | H | H | H | H | H | H |
| portkey | outage_fallback | A | A | R(b) | R(b) | R(b) | H | H | H | H | H | H |
| portkey | outage_fallback_wildcard | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS |
| portkey | content_policy_fallback | A | A | H | R(b) | R(b) | H | H | H | H | H | H |
| portkey | offlist_fallback | A | A | R(z) | R(z) | R(z) | H | H | H | H | H | H |
| portkey | refusal_failover | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS |

Deployer guardrail rows (upstream scenario `ok`; two prompt kinds):

| Router | Config | blocked prompt | allowed prompt |
|---|---|---|---|
| portkey | guardrail_fallback | R(b) | A |
| portkey | guardrail_control | H | A |
| litellm | guardrail_fallback | NS | NS |
| litellm | guardrail_control | NS | NS |
| langchain | guardrail_fallback | NS | NS |
| langchain | guardrail_control | NS | NS |

Reading the log:
- `guardrail_control` is logged as `config: "default"` with `refusal_kind: "deployer_guardrail"`.
- `ok_toolcall` lines have `answering_model: null` and `refusal_returned_to_caller: true`, because the runner reads `ANSWERED_BY` from message text and a tool call has none. mock-a answered; these are not refusals. Exclude them from any refusal-held count.
- `ERR` cell (langchain / refusal_failover / ok_toolcall): all 3 reps raised `AttributeError: 'NoneType' object has no attribute 'text'` inside the adapter, so the outcome fields are null. The run did not crash, so the adapter was not changed.

## c) Findings

- **200-OK refusals are re-routed only by specific configs.**
  - Rerouted to mock-b: LiteLLM `content_policy_fallback` and `outage_fallback_wildcard` on `oa200_content_filter`, `an200_refusal`, `an200_refusal_nodetails`, `gem200_safety`; LangChain `refusal_failover` on `oa200_content_filter` and `oa200_refusal_field`.
  - All 200-OK refusal scenarios held under every `default` and `outage_fallback` row, and under every Portkey row.
  - `text_refusal` held in every supported cell.
- **LiteLLM `content_policy_fallbacks` and plain `fallbacks` cover opposite sets.**
  - `outage_fallback`: `http500`, `http400_policy`, `azure400_filter` rerouted; the four 200-OK `content_filter` cases held.
  - `content_policy_fallback`: the reverse. Those four rerouted; `http500`, `http400_policy`, `azure400_filter` held.
  - `outage_fallback_wildcard` reroutes the union of both sets (7 of the 7 scenarios above).
  - `oa200_refusal_field` held in all three.
- **Generic fallback re-routes HTTP 400 refusals in all three routers.** `http400_policy` and `azure400_filter` are R(b) under `outage_fallback` for LiteLLM, LangChain and Portkey. Portkey `content_policy_fallback` (`on_status_codes: [400]`) reroutes those two and holds `http500`.
- **Portkey deployer guardrail (H2).**
  - `guardrail_fallback`, blocked prompt: R(b) in 3/3 reps, `blocked=false`; mock-b answered.
  - `guardrail_control`, blocked prompt: H in 3/3, `blocked=true`, no model received the request.
  - Allowed prompts reached mock-a in both configs with no re-route.
- **Off-list escapes (H3).** `offlist_fallback` reached mock-z on `http500`, `http400_policy` and `azure400_filter` in all three routers: 9 cells, 27 lines, `within_allowlist=false`. The config uses generic fallback, so 200-OK refusals held in those rows; no off-list target was tested with content-policy or wildcard fallback.
- **Reps were deterministic.** 0 of 141 executed cells differed across reps.

## d) Disclosure and LiteLLM mapping

### Disclosure (step 4): `outage_fallback` + `http500`, OpenAI style

All three answered 200 from mock-b. Header names come through `safe_headers`; no values were printed.

| Router | Header names | Model named in headers | Model named in body |
|---|---|---|---|
| litellm | x-litellm-attempted-fallbacks, x-litellm-attempted-retries, x-litellm-model-api-base, x-litellm-model-group, x-litellm-model-id | Only x-litellm-model-api-base contains `mock-b` | Yes (`model` is exactly `mock-b`) |
| langchain | none | No | Yes (`model` is exactly `mock-b`) |
| portkey | none | No | Yes (`model` is exactly `mock-b`) |

Limits on these results:
- LiteLLM runs in-process, so its "headers" are built by the adapter from `_hidden_params`, not read from HTTP.
- `x-litellm-model-api-base` contains `mock-b` because the mock's URL path carries the label (PLAN.md 4.1).
- The LangChain adapter does not read headers, so "none" means none captured, not none sent.
- Portkey: `safe_headers` keeps `x-portkey-*` names and none came through. The gateway source defines `x-portkey-last-used-option-index` and `x-portkey-retry-attempt-count` (build/start-server.js:2, minified). Headers outside the `safe_headers` prefixes were not inspected.
- `disclosed_in_response` was true on all 111 rerouted lines. For LangChain and Portkey the only source is the body `model` field, which the mock sets to its label.

### LiteLLM 1.108.3 mapping (step 5)

Paths are relative to `.venv/Lib/site-packages/litellm/`. `eu` = `litellm_core_utils/exception_mapping_utils.py`.

`ContentPolicyViolationError` always carries `status_code = 400` (`exceptions.py:690`). None of the sites below check an upstream status code, except where stated.

| Site | Applies to | Condition |
|---|---|---|
| `eu:317-318` | OpenAI-family | body `error.code == "cyber_policy"` (`eu:286`) |
| `eu:380-385` | OpenAI-family | `"invalid_request_error"` AND `"content_policy_violation"` in error_str; OR `"Invalid prompt"` AND `"violating our usage policy"`; OR `"request was rejected as a result of the safety system"` (lower-cased) |
| `eu:599-600` | anthropic | `"content filtering policy"` in error_str |
| `eu:1269-1273` | Vertex / Gemini | `"The response was blocked."` or `"Output blocked by content filtering policy"`; built with response status 400 (`eu:1279`) |
| `eu:2045-2052` | azure | body code `content_policy_violation`, inner code `ResponsibleAIPolicyViolation` (`eu:2012-2015`), or a substring in `eu:128-136`: `content_policy_violation`, `responsibleaipolicyviolation`, `the response was filtered due to the prompt triggering azure openai's content management`, `your task failed as a result of our safety system`, `the model produced invalid content`, `content_filter_policy`, `your request was rejected as a result of our safety system` |
| `router.py:2962-2966` (sync), `router.py:4161-4167` (async) | 200 responses | `choices[0].finish_reason == "content_filter"` and a content-policy fallback is available (`router.py:9242-9254`) |

- `finish_reason` normalisation: `litellm_core_utils/core_helpers.py:240` maps `refusal` to `content_filter`; `:253` maps `SAFETY` to `content_filter`.
- Availability: `router.py:9144-9161`. A configured `content_policy_fallbacks` list resolves for the group, or a `"*"` default fallback exists.
- Dispatch: `router.py:8065-8087`. With no content-policy list, execution continues to generic fallbacks (`router.py:8097`).
- A 400 reaching no substring match becomes `BadRequestError` (`eu:463-464`).

Adapter deployments use the `openai/` prefix for OpenAI-style scenarios, so `_map_openai_exception` applies (`eu:2540-2547`), not the azure branch.

Which scenarios should trigger `content_policy_fallbacks`, by that code, compared with the run:

| Scenario | Expected by code | Observed (`content_policy_fallback`) |
|---|---|---|
| oa200_content_filter | Yes: finish_reason is content_filter | R(b) |
| an200_refusal | Yes: refusal maps to content_filter | R(b) |
| an200_refusal_nodetails | Yes: refusal maps to content_filter | R(b) |
| gem200_safety | Yes: SAFETY maps to content_filter | R(b) |
| http400_policy | No: see below | H |
| azure400_filter | No on `openai/`: see below | H |
| oa200_refusal_field | No: finish_reason is stop | H |
| text_refusal | No: finish_reason is stop | H |
| ok, ok_toolcall | No | A |
| http500 | No: not a 400 policy error | H |

Code and observation agree on all 11.

The `http400_policy` result was checked by wrapping `_map_openai_exception` in a diagnostic run:
- `error_str` was `Error code: 400 - Your request was rejected as a result of our safety system.`
- The `code` and `type` fields were not in that string, so `eu:381` was false. `eu:383` looks for "the safety system" while the body says "our safety system", so it was false too.
- LiteLLM raised `BadRequestError` (status 400). `outage_fallback` then rerouted it through generic fallbacks.
- `azure400_filter` reached the same mapper and also raised `BadRequestError`. An actual `azure/` deployment was NOT RUN.

## LiteLLM proxy guardrail

Mock provider only, non-streaming, OpenAI style. litellm 1.108.3 proxy on 127.0.0.1:4000. Run 2026-11-08, `run_id` 56f05ea7a8d242009a77b1a29b589802, 3 reps, 48 log lines (24 executed, 24 `not_supported`). Command: `AVAILABLE_SCENARIOS=ok,http500 python run.py --exp A --router litellm_proxy --reps 3`. Outcomes come from `logs/mock_requests.jsonl`.

Exclude `run_id` 7b64ebc7022c41b6b846f844ac2c6586 (48 lines) from `logs/exp_A.jsonl`: every proxy start failed on a console-encoding crash, since fixed, so its 24 executed-cell lines have null outcomes.

| Config | blocked prompt | allowed prompt |
|---|---|---|
| guardrail_fallback (guardrail on primary, fallbacks mock-a → mock-b) | H 3/3: HTTP 446, `blocked=true`, no model received it | A 3/3 |
| guardrail_control (guardrail, no fallback) | H 3/3: HTTP 446, `blocked=true`, no model received it | A 3/3 |

Controls, 3/3 each: `default` + `ok` A; `default` + `http500` H (500 returned); `outage_fallback` + `ok` A; `outage_fallback` + `http500` R(b).

**H2 did not reproduce on this LiteLLM proxy setup.** A `pre_call` guardrail rejected the request and the configured fallback did not run. Portkey's `guardrail_fallback` re-routes the same prompt (R(b), section c).

Why, from the source (paths relative to `.venv/Lib/site-packages/litellm/`):
- Guardrail: subclass of `CustomGuardrail` (`integrations/custom_guardrail.py:337`) overriding `async_pre_call_hook`, called from `proxy/utils.py:2376-2377` once `should_run_guardrail` passes (`proxy/utils.py:2471`).
- Primary-only scoping works: `litellm_params.guardrails` is set on the mock-a deployments only. Before routing, the proxy takes the union of guardrails across the requested group's deployments (`proxy/utils.py:9111-9126`) and merges them (`proxy/common_request_processing.py:2444`).
- The hook runs at `proxy/common_request_processing.py:2461`, before a deployment is chosen (comment at `:2432`). The exception ends the request there, so the router's fallback code is not entered.

Limits on this result:
- Only `mode: pre_call` was run. `during_call`, `post_call` and a guardrail overriding `async_pre_call_deployment_hook` are NOT RUN, and could behave differently because they run alongside or inside the router call.
- Read but NOT RUN: router fallback is skipped for a guardrail intervention (`router.py:7923`, `router.py:8343`), which `integrations/custom_guardrail.py:91-109` defines to include `HTTPException` 400, 403 and 422, not 446.
- The block status 446 is our choice, matching Portkey's deny, because `routers/runner.py` counts only that status as a block with no provider hit. By the code above it should not change the pre-call path; a 400 block was NOT RUN.
- `reported_model` is the proxy's model group, not the provider label: `mock-a--ok` for primary answers. The fallback group is named `mock-b`, the same as its label, so `disclosed_in_response=true` on `http500` says little by itself. `x-litellm-model-name` did name `openai/mock-b`.

Setup needed on Windows with 1.108.3:
- The proxy exits with code 3 at start-up without `PYTHONUTF8=1` (`UnicodeEncodeError` in the cp1252 console encoder).
- It refuses to start with no master key (`proxy/auth/master_key_boot_check.py:95`). The adapter passes the dummy key as `LITELLM_MASTER_KEY` in the child's environment and does not use the "dangerously permit" override.
