# Table 1 - Exp A conformance (mock provider)

Versions: langchain 1.7.6; litellm 1.108.3; litellm_proxy 1.108.3; portkey 1.15.2. Run time (UTC): 2026-11-08T16:47:52Z to 2026-11-08T17:24:58Z. run_ids: 2. Reps: [0, 1, 2]. Rows after filters: 678.

`A` primary (mock-a) answered, no re-route. `H` held: no re-route and no answer (refusal or error returned). `R(b)` re-routed to the approved fallback mock-b. `R(z)` re-routed to the off-list mock-z. `NS` not supported by that router/config. `ERR` no outcome recorded. `!` outcome differed across reps (majority shown). `.` not run (litellm_proxy was run on `ok` and `http500` only). `ok`, `ok_toolcall`, `http500` are controls.

## Refusal scenarios

| router | config | ok | ok_toolcall | http500 | http400_policy | azure400_filter | oa200_content_filter | oa200_refusal_field | text_refusal | an200_refusal | an200_refusal_nodetails | gem200_safety |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| litellm | default | A | A | H | H | H | H | H | H | H | H | H |
| litellm | outage_fallback | A | A | R(b) | R(b) | R(b) | H | H | H | H | H | H |
| litellm | outage_fallback_wildcard | A | A | R(b) | R(b) | R(b) | R(b) | H | H | R(b) | R(b) | R(b) |
| litellm | content_policy_fallback | A | A | H | H | H | R(b) | H | H | R(b) | R(b) | R(b) |
| litellm | refusal_failover | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS |
| litellm | offlist_fallback | A | A | R(z) | R(z) | R(z) | H | H | H | H | H | H |
| litellm_proxy | default | A | . | H | . | . | . | . | . | . | . | . |
| litellm_proxy | outage_fallback | A | . | R(b) | . | . | . | . | . | . | . | . |
| litellm_proxy | outage_fallback_wildcard | NS | . | NS | . | . | . | . | . | . | . | . |
| litellm_proxy | content_policy_fallback | NS | . | NS | . | . | . | . | . | . | . | . |
| litellm_proxy | refusal_failover | NS | . | NS | . | . | . | . | . | . | . | . |
| litellm_proxy | offlist_fallback | NS | . | NS | . | . | . | . | . | . | . | . |
| langchain | default | A | A | H | H | H | H | H | H | H | H | NS |
| langchain | outage_fallback | A | A | R(b) | R(b) | R(b) | H | H | H | H | H | NS |
| langchain | outage_fallback_wildcard | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS |
| langchain | content_policy_fallback | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS |
| langchain | refusal_failover | A | ERR | R(b) | R(b) | R(b) | R(b) | R(b) | H | NS | NS | NS |
| langchain | offlist_fallback | A | A | R(z) | R(z) | R(z) | H | H | H | H | H | NS |
| portkey | default | A | A | H | H | H | H | H | H | H | H | H |
| portkey | outage_fallback | A | A | R(b) | R(b) | R(b) | H | H | H | H | H | H |
| portkey | outage_fallback_wildcard | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS |
| portkey | content_policy_fallback | A | A | H | R(b) | R(b) | H | H | H | H | H | H |
| portkey | refusal_failover | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS | NS |
| portkey | offlist_fallback | A | A | R(z) | R(z) | R(z) | H | H | H | H | H | H |


## Deployer guardrail (upstream scenario `ok`)

| router | config | blocked prompt | allowed prompt |
|---|---|---|---|
| litellm | guardrail_fallback | NS | NS |
| litellm | guardrail_control | NS | NS |
| litellm_proxy | guardrail_fallback | H | A |
| litellm_proxy | guardrail_control | H | A |
| langchain | guardrail_fallback | NS | NS |
| langchain | guardrail_control | NS | NS |
| portkey | guardrail_fallback | R(b) | A |
| portkey | guardrail_control | H | A |
