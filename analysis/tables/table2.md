# Table 2 - Exp C agent consequences (LiteLLM gateway, mock provider)

Versions: litellm/langgraph litellm 1.108.3; langgraph 1.2.20; langchain-openai 1.7.4; litellm/openai_agents litellm 1.108.3; openai-agents 0.24.0. Run time (UTC): 2026-11-08T10:26:43Z to 2026-11-08T10:34:03Z. run_ids: 1. Reps: [0, 1, 2]. Rows after filters: 300.

Cells are k/n sessions pooled over the 5 gateway configs (3 reps each). `session_pinned` is defined only for sessions re-routed on turn 1, so its n differs.

## Framework x scenario

| framework | scenario | sessions | re-routed | tool_call_executed | trace_names_model | session_pinned |
|---|---|---|---|---|---|---|
| langgraph | ok_toolcall | 15 | 0/15 | 15/15 | 0/15 | n/a (n=0) |
| langgraph | http500 | 15 | 9/15 | 9/15 | 9/9 | 0/9 |
| langgraph | http400_policy | 15 | 9/15 | 9/15 | 9/9 | 0/9 |
| langgraph | azure400_filter | 15 | 12/15 | 12/15 | 12/12 | 0/12 |
| langgraph | oa200_content_filter | 15 | 9/15 | 9/15 | 9/9 | 0/9 |
| langgraph | oa200_refusal_field | 15 | 0/15 | 0/15 | n/a (n=0) | n/a (n=0) |
| langgraph | text_refusal | 15 | 0/15 | 0/15 | n/a (n=0) | n/a (n=0) |
| langgraph | an200_refusal | 15 | 9/15 | 9/15 | 9/9 | 0/9 |
| langgraph | an200_refusal_nodetails | 15 | 9/15 | 9/15 | 9/9 | 0/9 |
| langgraph | gem200_safety | 15 | 9/15 | 9/15 | 9/9 | 0/9 |
| openai_agents | ok_toolcall | 15 | 0/15 | 15/15 | 0/15 | n/a (n=0) |
| openai_agents | http500 | 15 | 9/15 | 9/15 | 0/9 | 0/9 |
| openai_agents | http400_policy | 15 | 9/15 | 9/15 | 0/9 | 0/9 |
| openai_agents | azure400_filter | 15 | 12/15 | 12/15 | 0/12 | 0/12 |
| openai_agents | oa200_content_filter | 15 | 9/15 | 9/15 | 0/9 | 0/9 |
| openai_agents | oa200_refusal_field | 15 | 0/15 | 0/15 | n/a (n=0) | n/a (n=0) |
| openai_agents | text_refusal | 15 | 0/15 | 0/15 | n/a (n=0) | n/a (n=0) |
| openai_agents | an200_refusal | 15 | 9/15 | 9/15 | 0/9 | 0/9 |
| openai_agents | an200_refusal_nodetails | 15 | 9/15 | 9/15 | 0/9 | 0/9 |
| openai_agents | gem200_safety | 15 | 9/15 | 9/15 | 0/9 | 0/9 |


## Per gateway config (pooled over frameworks)

`A` primary answered; `H` held (refusal/error reached the agent); `R(b|z) k/n` re-routed to mock-b / off-list mock-z; `tool` = fallback's tool call executed in every re-routed session.

| scenario | default | outage_fallback | outage_fallback_wildcard | content_policy_fallback | offlist_fallback |
|---|---|---|---|---|---|
| ok_toolcall | A | A | A | A | A |
| http500 | H | R(b) 6/6 tool | R(b) 6/6 tool | H | R(z) 6/6 tool |
| http400_policy | H | R(b) 6/6 tool | R(b) 6/6 tool | H | R(z) 6/6 tool |
| azure400_filter | H | R(b) 6/6 tool | R(b) 6/6 tool | R(b) 6/6 tool | R(z) 6/6 tool |
| oa200_content_filter | H | H | R(b) 6/6 tool | R(b) 6/6 tool | R(z) 6/6 tool |
| oa200_refusal_field | H | H | H | H | H |
| text_refusal | H | H | H | H | H |
| an200_refusal | H | H | R(b) 6/6 tool | R(b) 6/6 tool | R(z) 6/6 tool |
| an200_refusal_nodetails | H | H | R(b) 6/6 tool | R(b) 6/6 tool | R(z) 6/6 tool |
| gem200_safety | H | H | R(b) 6/6 tool | R(b) 6/6 tool | R(z) 6/6 tool |


## H4: who names the answering model (re-routed sessions, Wilson 95% CI)

| framework | re-routed sessions | gateway names answering model | framework trace names answering model | tool call executed | session pinned |
|---|---|---|---|---|---|
| langgraph | 66 | 66/66 = 100.0% [95% CI 94.5%, 100.0%] | 66/66 = 100.0% [95% CI 94.5%, 100.0%] | 66/66 = 100.0% [95% CI 94.5%, 100.0%] | 0/66 = 0.0% [95% CI 0.0%, 5.5%] |
| openai_agents | 66 | 66/66 = 100.0% [95% CI 94.5%, 100.0%] | 0/66 = 0.0% [95% CI 0.0%, 5.5%] | 66/66 = 100.0% [95% CI 94.5%, 100.0%] | 0/66 = 0.0% [95% CI 0.0%, 5.5%] |
