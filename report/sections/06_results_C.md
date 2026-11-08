# §6 Results C — Agent consequences of a re-routed refusal

*Setup: §3.y. LiteLLM 1.108.3 proxy as gateway; openai-agents 0.24.0 and langgraph 1.2.20 /
langchain-openai 1.7.4; mock provider only. Run date 2026-11-08. 5 configs × 2 frameworks ×
10 scenarios × 3 reps = 300 two-turn sessions (run id `2e4e9268…`). All three reps of every cell gave
the same outcome. Rates carry Wilson 95% intervals. The mock is deterministic, so these intervals
describe repeatability under the stated configs, not variation across deployments.*

**What a fallback config re-routes (Table 2a).** We call this documented behaviour under stated
configs, not a bypass: with LiteLLM's default config (no fallbacks), none of the 8 refusal scenarios
or the outage was re-routed. In each case the refusal or error reached the agent (54/54 sessions).
Once a fallback is configured, which kind of "no" gets re-routed depends on which option was used,
in ways the option names do not suggest:

- `content_policy_fallbacks` re-routed every **200-OK provider refusal** (OpenAI
  `finish_reason: content_filter`, Anthropic `stop_reason: refusal` with and without
  `stop_details`, Gemini `SAFETY`) and the Azure 400 `content_filter` error. It did **not**
  re-route OpenAI's own HTTP 400 `content_policy_violation`, which reached the agent as a
  `BadRequestError`.
- Plain per-group `fallbacks` (the "outage" option) did the reverse. They re-routed both HTTP 400
  policy errors and the 500, but none of the 200-OK refusals.
- A wildcard `"*"` fallback re-routed **every provider-level refusal**: both 400s and all four
  200-OK formats. This supports H1.
- Neither option re-routed **model-level** refusals (`message.refusal`, or a plain-text "I can't help
  with that."). The gateway passes these through as ordinary 200 answers.

**Refused actions still ran.** In every re-routed session (132/132 = 100% [97%, 100%]), the
fallback model's `write_record` call was executed and the row was written. The agent therefore
performed the action that the primary model had refused. Under `offlist_fallback`, all 42 re-routed
sessions (42/42 = 100% [92%, 100%]) were answered by `mock-z`, a model **outside the approved list**,
and its tool call ran. This supports H3: the gateway does not check the approved list, and neither
agent framework did either.

**No session stickiness: the refusal is re-routed silently at every step.** In all 132 re-routed
sessions the gateway called the refusing primary first on **every** model call: 4 primary refusals
and 4 fallback answers per two-turn session (the tool-call step and the post-tool step in each turn).
Turn 2 was never pinned to the fallback (0/132 = 0% [0%, 3%]). An agent behind this gateway can
therefore receive a refusal, have it overridden, and do the same again later in the same session,
with no signal at the agent layer that anything happened.

**Who records which model answered (H4).** LiteLLM always disclosed the fallback in its response:
on fallback, both the body `model` field (`mock-b`/`mock-z`) and `x-litellm-model-api-base` named
the answering model, and `x-litellm-attempted-fallbacks: 1` was set (66/66 per framework). Whether
the *agent's own trace* kept that information depended entirely on the framework:

| framework | re-routed sessions | gateway names model | framework trace names model |
|---|---|---|---|
| LangGraph + langchain-openai | 66 | 66/66 = 100% [94%, 100%] | 66/66 = 100% [94%, 100%] |
| OpenAI Agents SDK | 66 | 66/66 = 100% [94%, 100%] | **0/66 = 0% [0%, 6%]** |

The Agents SDK's generation span stores only the model name the agent *requested* (for example
`agent-oa200_content_filter`). The response's `model` field and the gateway headers are never
written to the trace, so a team auditing Agents SDK traces cannot tell that a different model
answered. LangChain copies the response's `model` field into `response_metadata.model_name`, so its
trace names the fallback. This works only because LiteLLM passes the upstream model name through on
the fallback path. On the normal path LiteLLM rewrites the body `model` to the model-group alias
(`agent-ok_toolcall` in 60/60 control sessions), so even LangChain's trace records an alias rather
than the model that answered.

**When nothing re-routes, the frameworks disagree on what a refusal is.** LiteLLM normalises
Anthropic `stop_reason: refusal` and Gemini `SAFETY` to OpenAI `finish_reason: content_filter`. Given
that response, the Agents SDK raised `ModelRefusalError` (24/24 sessions). LangGraph returned an
**empty final answer with no error** (24/24), so a LangGraph agent cannot tell a provider refusal
apart from an empty reply unless it inspects `finish_reason` itself.

**Takeaways for agent infrastructure.** (1) The fallback option a deployer picks decides which kinds
of "no" an agent can be routed around, and the names (`content_policy_fallbacks` vs `fallbacks`) do
not predict the result. (2) A re-routed refusal becomes an executed tool call, and the approved-list
check must happen at the gateway, because the agent never sees the model switch. (3) Agent traces
need the *responding* model, not only the requested one, or a re-route cannot be audited after the
fact.

*Limitations specific to Exp C:* one gateway (LiteLLM 1.108.3), so other routers' agent-level
behaviour is not measured here (Exp A covers routers without an agent); mock provider only;
non-streaming only; one tool. Model-level refusals were never re-routed under any LiteLLM option,
so we cannot say what an agent would do with a re-routed model-level refusal.
