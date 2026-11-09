# Cross-check - Exp A vs Exp C on LiteLLM 1.108.3

The same LiteLLM version measured by two independent harnesses: Role B's router runner (in-process LiteLLM, Exp A) and Role A's agent harness (LiteLLM proxy behind two agent frameworks, Exp C). Codes as in Table 1; Exp C pooled over frameworks and reps.

| config | scenario | Exp A (litellm in-process) | Exp C (litellm proxy + agents) | verdict | explanation |
|---|---|---|---|---|---|
| default | ok_toolcall | A | A | agree |  |
| default | http500 | H | H | agree |  |
| default | http400_policy | H | H | agree |  |
| default | azure400_filter | H | H | agree |  |
| default | oa200_content_filter | H | H | agree |  |
| default | oa200_refusal_field | H | H | agree |  |
| default | text_refusal | H | H | agree |  |
| default | an200_refusal | H | H | agree |  |
| default | an200_refusal_nodetails | H | H | agree |  |
| default | gem200_safety | H | H | agree |  |
| outage_fallback | ok_toolcall | A | A | agree |  |
| outage_fallback | http500 | R(b) | R(b) | agree |  |
| outage_fallback | http400_policy | R(b) | R(b) | agree |  |
| outage_fallback | azure400_filter | R(b) | R(b) | agree |  |
| outage_fallback | oa200_content_filter | H | H | agree |  |
| outage_fallback | oa200_refusal_field | H | H | agree |  |
| outage_fallback | text_refusal | H | H | agree |  |
| outage_fallback | an200_refusal | H | H | agree |  |
| outage_fallback | an200_refusal_nodetails | H | H | agree |  |
| outage_fallback | gem200_safety | H | H | agree |  |
| outage_fallback_wildcard | ok_toolcall | A | A | agree |  |
| outage_fallback_wildcard | http500 | R(b) | R(b) | agree |  |
| outage_fallback_wildcard | http400_policy | R(b) | R(b) | agree |  |
| outage_fallback_wildcard | azure400_filter | R(b) | R(b) | agree |  |
| outage_fallback_wildcard | oa200_content_filter | R(b) | R(b) | agree |  |
| outage_fallback_wildcard | oa200_refusal_field | H | H | agree |  |
| outage_fallback_wildcard | text_refusal | H | H | agree |  |
| outage_fallback_wildcard | an200_refusal | R(b) | R(b) | agree |  |
| outage_fallback_wildcard | an200_refusal_nodetails | R(b) | R(b) | agree |  |
| outage_fallback_wildcard | gem200_safety | R(b) | R(b) | agree |  |
| content_policy_fallback | ok_toolcall | A | A | agree |  |
| content_policy_fallback | http500 | H | H | agree |  |
| content_policy_fallback | http400_policy | H | H | agree |  |
| content_policy_fallback | azure400_filter | H | R(b) | differ (explained) | Exp A sends the Azure body through LiteLLM's `openai/` adapter (BadRequestError); Exp C uses a real `azure/` deployment, whose mapper raises ContentPolicyViolationError |
| content_policy_fallback | oa200_content_filter | R(b) | R(b) | agree |  |
| content_policy_fallback | oa200_refusal_field | H | H | agree |  |
| content_policy_fallback | text_refusal | H | H | agree |  |
| content_policy_fallback | an200_refusal | R(b) | R(b) | agree |  |
| content_policy_fallback | an200_refusal_nodetails | R(b) | R(b) | agree |  |
| content_policy_fallback | gem200_safety | R(b) | R(b) | agree |  |
| offlist_fallback | ok_toolcall | A | A | agree |  |
| offlist_fallback | http500 | R(z) | R(z) | agree |  |
| offlist_fallback | http400_policy | R(z) | R(z) | agree |  |
| offlist_fallback | azure400_filter | R(z) | R(z) | agree |  |
| offlist_fallback | oa200_content_filter | H | R(z) | differ (explained) | Exp A `offlist_fallback` sets generic `fallbacks` only; Exp C's also sets `content_policy_fallbacks` (agent_exp/gateway.py) |
| offlist_fallback | oa200_refusal_field | H | H | agree |  |
| offlist_fallback | text_refusal | H | H | agree |  |
| offlist_fallback | an200_refusal | H | R(z) | differ (explained) | Exp A `offlist_fallback` sets generic `fallbacks` only; Exp C's also sets `content_policy_fallbacks` (agent_exp/gateway.py) |
| offlist_fallback | an200_refusal_nodetails | H | R(z) | differ (explained) | Exp A `offlist_fallback` sets generic `fallbacks` only; Exp C's also sets `content_policy_fallbacks` (agent_exp/gateway.py) |
| offlist_fallback | gem200_safety | H | R(z) | differ (explained) | Exp A `offlist_fallback` sets generic `fallbacks` only; Exp C's also sets `content_policy_fallbacks` (agent_exp/gateway.py) |
