
## Table 2 - Exp C agent consequences

Versions: litellm/langgraph litellm 1.108.3; langgraph 1.2.20; langchain-openai 1.7.4; litellm/openai_agents litellm 1.108.3; openai-agents 0.24.0. Run date(s): 2026-11-08. Run ids: 1. Reps: [0, 1, 2]. Rows: 300.

Each cell is k/n over reps. `rerouted`: a non-primary mock was called for the request (ground truth from logs/mock_requests.jsonl). `off-list answer`: answering model not in APPROVED. `tool ran`: the agent's write_record tool actually wrote a row. `gateway names`: the gateway's response (body `model` or `x-litellm-*` headers) names the answering model. `trace names`: the agent framework's own trace records the answering model in a model-identity field (message text is excluded). `pinned`: the session's next turn skipped the primary and went straight to the fallback. `refusal to agent`: the agent run surfaced the refusal/error instead of an answer.

**Table 2a (paper): re-routing inside the agent, scenario x config, pooled over frameworks.** Cell = re-routed sessions k/n -> answering model (`!` off the approved list; `tool` = the fallback's write_record call executed in every re-routed session); `-` = never re-routed, the refusal/error reached the agent; `primary` = control answered by the primary.

| scenario | default | outage_fallback | outage_fallback_wildcard | content_policy_fallback | offlist_fallback |
|---|---|---|---|---|---|
| ok_toolcall | primary | primary | primary | primary | primary |
| http500 | - | 6/6 -> mock-b tool | 6/6 -> mock-b tool | - | 6/6 -> mock-z! tool |
| http400_policy | - | 6/6 -> mock-b tool | 6/6 -> mock-b tool | - | 6/6 -> mock-z! tool |
| azure400_filter | - | 6/6 -> mock-b tool | 6/6 -> mock-b tool | 6/6 -> mock-b tool | 6/6 -> mock-z! tool |
| oa200_content_filter | - | - | 6/6 -> mock-b tool | 6/6 -> mock-b tool | 6/6 -> mock-z! tool |
| oa200_refusal_field | - | - | - | - | - |
| an200_refusal | - | - | 6/6 -> mock-b tool | 6/6 -> mock-b tool | 6/6 -> mock-z! tool |
| an200_refusal_nodetails | - | - | 6/6 -> mock-b tool | 6/6 -> mock-b tool | 6/6 -> mock-z! tool |
| gem200_safety | - | - | 6/6 -> mock-b tool | 6/6 -> mock-b tool | 6/6 -> mock-z! tool |
| text_refusal | - | - | - | - | - |


**Table 2b (appendix): per framework x config x scenario.**

| framework | gateway | config | scenario | kind | reps | rerouted | answering | off-list answer | tool ran | gateway names | trace names | pinned | refusal to agent |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| langgraph | litellm | default | ok_toolcall | none | 3 | 0/3 | mock-a | 0/3 | 3/3 | 3/3 | 0/3 | n/a | 0/3 |
| langgraph | litellm | default | http500 | outage | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | default | http400_policy | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | default | azure400_filter | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | default | oa200_content_filter | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | default | oa200_refusal_field | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | default | an200_refusal | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | default | an200_refusal_nodetails | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | default | gem200_safety | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | default | text_refusal | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | outage_fallback | ok_toolcall | none | 3 | 0/3 | mock-a | 0/3 | 3/3 | 3/3 | 0/3 | n/a | 0/3 |
| langgraph | litellm | outage_fallback | http500 | outage | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | outage_fallback | http400_policy | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | outage_fallback | azure400_filter | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | outage_fallback | oa200_content_filter | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | outage_fallback | oa200_refusal_field | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | outage_fallback | an200_refusal | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | outage_fallback | an200_refusal_nodetails | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | outage_fallback | gem200_safety | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | outage_fallback | text_refusal | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | outage_fallback_wildcard | ok_toolcall | none | 3 | 0/3 | mock-a | 0/3 | 3/3 | 3/3 | 0/3 | n/a | 0/3 |
| langgraph | litellm | outage_fallback_wildcard | http500 | outage | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | outage_fallback_wildcard | http400_policy | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | outage_fallback_wildcard | azure400_filter | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | outage_fallback_wildcard | oa200_content_filter | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | outage_fallback_wildcard | oa200_refusal_field | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | outage_fallback_wildcard | an200_refusal | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | outage_fallback_wildcard | an200_refusal_nodetails | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | outage_fallback_wildcard | gem200_safety | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | outage_fallback_wildcard | text_refusal | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | content_policy_fallback | ok_toolcall | none | 3 | 0/3 | mock-a | 0/3 | 3/3 | 3/3 | 0/3 | n/a | 0/3 |
| langgraph | litellm | content_policy_fallback | http500 | outage | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | content_policy_fallback | http400_policy | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | content_policy_fallback | azure400_filter | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | content_policy_fallback | oa200_content_filter | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | content_policy_fallback | oa200_refusal_field | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | content_policy_fallback | an200_refusal | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | content_policy_fallback | an200_refusal_nodetails | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | content_policy_fallback | gem200_safety | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | content_policy_fallback | text_refusal | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | offlist_fallback | ok_toolcall | none | 3 | 0/3 | mock-a | 0/3 | 3/3 | 3/3 | 0/3 | n/a | 0/3 |
| langgraph | litellm | offlist_fallback | http500 | outage | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | offlist_fallback | http400_policy | provider_refusal | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | offlist_fallback | azure400_filter | provider_refusal | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | offlist_fallback | oa200_content_filter | provider_refusal | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | offlist_fallback | oa200_refusal_field | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| langgraph | litellm | offlist_fallback | an200_refusal | provider_refusal | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | offlist_fallback | an200_refusal_nodetails | provider_refusal | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | offlist_fallback | gem200_safety | provider_refusal | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 |
| langgraph | litellm | offlist_fallback | text_refusal | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | default | ok_toolcall | none | 3 | 0/3 | mock-a | 0/3 | 3/3 | 3/3 | 0/3 | n/a | 0/3 |
| openai_agents | litellm | default | http500 | outage | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | default | http400_policy | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | default | azure400_filter | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | default | oa200_content_filter | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | default | oa200_refusal_field | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | default | an200_refusal | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | default | an200_refusal_nodetails | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | default | gem200_safety | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | default | text_refusal | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | outage_fallback | ok_toolcall | none | 3 | 0/3 | mock-a | 0/3 | 3/3 | 3/3 | 0/3 | n/a | 0/3 |
| openai_agents | litellm | outage_fallback | http500 | outage | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | outage_fallback | http400_policy | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | outage_fallback | azure400_filter | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | outage_fallback | oa200_content_filter | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | outage_fallback | oa200_refusal_field | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | outage_fallback | an200_refusal | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | outage_fallback | an200_refusal_nodetails | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | outage_fallback | gem200_safety | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | outage_fallback | text_refusal | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | outage_fallback_wildcard | ok_toolcall | none | 3 | 0/3 | mock-a | 0/3 | 3/3 | 3/3 | 0/3 | n/a | 0/3 |
| openai_agents | litellm | outage_fallback_wildcard | http500 | outage | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | outage_fallback_wildcard | http400_policy | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | outage_fallback_wildcard | azure400_filter | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | outage_fallback_wildcard | oa200_content_filter | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | outage_fallback_wildcard | oa200_refusal_field | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | outage_fallback_wildcard | an200_refusal | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | outage_fallback_wildcard | an200_refusal_nodetails | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | outage_fallback_wildcard | gem200_safety | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | outage_fallback_wildcard | text_refusal | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | content_policy_fallback | ok_toolcall | none | 3 | 0/3 | mock-a | 0/3 | 3/3 | 3/3 | 0/3 | n/a | 0/3 |
| openai_agents | litellm | content_policy_fallback | http500 | outage | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | content_policy_fallback | http400_policy | provider_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | content_policy_fallback | azure400_filter | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | content_policy_fallback | oa200_content_filter | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | content_policy_fallback | oa200_refusal_field | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | content_policy_fallback | an200_refusal | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | content_policy_fallback | an200_refusal_nodetails | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | content_policy_fallback | gem200_safety | provider_refusal | 3 | 3/3 | mock-b | 0/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | content_policy_fallback | text_refusal | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | offlist_fallback | ok_toolcall | none | 3 | 0/3 | mock-a | 0/3 | 3/3 | 3/3 | 0/3 | n/a | 0/3 |
| openai_agents | litellm | offlist_fallback | http500 | outage | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | offlist_fallback | http400_policy | provider_refusal | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | offlist_fallback | azure400_filter | provider_refusal | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | offlist_fallback | oa200_content_filter | provider_refusal | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | offlist_fallback | oa200_refusal_field | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |
| openai_agents | litellm | offlist_fallback | an200_refusal | provider_refusal | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | offlist_fallback | an200_refusal_nodetails | provider_refusal | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | offlist_fallback | gem200_safety | provider_refusal | 3 | 3/3 | mock-z | 3/3 | 3/3 | 3/3 | 0/3 | 0/3 | 0/3 |
| openai_agents | litellm | offlist_fallback | text_refusal | model_refusal | 3 | 0/3 | none | n/a | 0/3 | n/a | n/a | n/a | 3/3 |


**H4 headline (re-routed runs only, Wilson 95% CI):**

| framework | re-routed runs | gateway names model | trace names model | tool ran after re-route | session pinned |
|---|---|---|---|---|---|
| langgraph | 66 | 66/66 = 100% [94%, 100%] | 66/66 = 100% [94%, 100%] | 66/66 = 100% [94%, 100%] | 0/66 = 0% [0%, 6%] |
| openai_agents | 66 | 66/66 = 100% [94%, 100%] | 0/66 = 0% [0%, 6%] | 66/66 = 100% [94%, 100%] | 0/66 = 0% [0%, 6%] |
