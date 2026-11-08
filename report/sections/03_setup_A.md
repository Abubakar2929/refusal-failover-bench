# §3 Threat model & setup — Role A part (mock provider, Exp C agent harness)

> Role B adds the router half of this section (routers, versions, configs for Exp A/B).

## 3.x Mock provider

All conformance (Exp A) and agent (Exp C) measurements run against a local mock provider
(`mock_provider/`, FastAPI). It needs no API keys and costs nothing, and it gives exact ground truth. The model
identity and the refusal scenario are encoded **in the URL path**. Routers generally let a deployer set
a per-deployment base URL, while custom headers may not be forwarded upstream, so the path is the most
portable place to carry them (Role B confirms per router in §3):

```
OpenAI     POST /p/{label}/{scenario}/v1/chat/completions
Anthropic  POST /p/{label}/{scenario}/v1/messages
Gemini     POST /p/{label}/{scenario}/v1beta/models/{model}:generateContent
Azure      POST /p/{label}/{scenario}/openai/deployments/{deployment}/chat/completions
```

`label` is the mock model identity: `mock-a` (primary), `mock-b` (approved fallback), `mock-z` (a model
**outside** the approved list). Every non-refused answer contains `ANSWERED_BY={label}`.

**Refusal scenarios (11).** One outage control (`http500`), two normal-answer controls (`ok`,
`ok_toolcall`), and eight refusal formats taken from provider documentation: OpenAI HTTP 400
`content_policy_violation`; Azure HTTP 400 `content_filter` with `innererror.ResponsibleAIPolicyViolation`;
OpenAI 200 `finish_reason: content_filter`; OpenAI 200 `message.refusal`; Anthropic 200
`stop_reason: refusal` with and without `stop_details`; Gemini 200 `finishReason: SAFETY`; and a plain
200 text refusal ("I can't help with that."). The bodies are copied byte-for-byte from
`contracts/refusal_formats.md`. The mock selftest fails if they drift. We added only fields that
real providers always send and that clients require: OpenAI `usage`, Gemini `usageMetadata` and
`modelVersion`. Without `usageMetadata`, LiteLLM 1.108.3 fails with `KeyError('usageMetadata')`.
That failure comes from the mock, not from the router, so we fixed the mock.

Each refusal scenario is served only on its native API style (for example, a Gemini `SAFETY` body is
never served on the OpenAI endpoint). Any other style gets HTTP 404 `scenario_not_native_to_style`,
so a misconfigured router cannot silently test the wrong format.

**Ground truth.** The mock appends every request it receives to `logs/mock_requests.jsonl`. Each entry
records label, scenario, HTTP status, whether the response was a refusal or a real answer, and the
request id. The request id is the `REQ:<uuid4>` tag, read from the last *user* message. Every outcome
we report about "which model was actually called" or "which model answered" comes from this file,
never from what a router or agent claims.

**Limitation.** The mock serves non-streaming responses only. `stream: true` is rejected with HTTP 400
`mock_streaming_not_supported`, so we did not test streaming refusal handling.

## 3.y Agent harness (Exp C)

Exp C asks what happens *inside an agent* when the gateway re-routes a refusal. We use two real
agent frameworks, each with one tool, `write_record(record_id, value)`. The tool writes a row to a
SQLite table, which is the observable side effect.

- **OpenAI Agents SDK** (`openai-agents` 0.24.0): `Agent` + `OpenAIChatCompletionsModel` + `Runner.run`.
- **LangGraph** (1.2.20, with `langchain-openai` 1.7.4): a two-node ReAct graph (model node,
  `ToolNode`), with an in-memory checkpointer holding the session.

Both agents use a **LiteLLM 1.108.3 proxy** as their `base_url`. One proxy runs per configuration:

| config | LiteLLM wiring (`litellm_settings`) |
|---|---|
| `default` | no fallbacks |
| `outage_fallback` | `fallbacks: agent-<s> → agent-fallback` |
| `outage_fallback_wildcard` | `fallbacks: "*" → agent-fallback` |
| `content_policy_fallback` | `content_policy_fallbacks: agent-<s> → agent-fallback` |
| `offlist_fallback` | `fallbacks` and `content_policy_fallbacks: agent-<s> → agent-offlist` |

The primary model group `agent-<s>` is `mock-a` serving refusal scenario *s*, called through the
LiteLLM provider adapter that matches the scenario's wire format (`openai/`, `azure/`, `anthropic/`,
`gemini/`). `agent-fallback` is `mock-b` and `agent-offlist` is `mock-z`; both serve `ok_toolcall`,
which asks the agent to call `write_record`. We set `num_retries: 0` in LiteLLM and `max_retries=0`
in both SDKs, so the mock log counts one call per routing decision. Every other setting is the
LiteLLM default.

Each session has two user turns with distinct request ids. For every session we record:

| field | definition |
|---|---|
| re-routed | the mock log shows a non-primary model called for turn 1 |
| answering model / off-list | last mock that returned a real answer for turn 1, and whether it is in {mock-a, mock-b} |
| tool ran | `write_record` actually wrote a row during turn 1 |
| gateway names model | a 200 response from the gateway names the answering model, either in the body `model` field or in any `x-litellm-*` header |
| trace names model | the framework's own trace names the answering model in a *model-identity* field (any key containing "model"); message text, tool arguments and base URLs are excluded, so the mock's `ANSWERED_BY=` tag cannot count |
| session pinned | (re-routed sessions only) turn 2 never called the primary but did call a fallback |
| refusal reached agent | turn 1 raised an error to the agent, or ended with no tool write and no answer from any model |

"Framework trace" means every span exported to an in-process `TracingProcessor` (Agents SDK; the
default exporter is replaced, so nothing leaves the machine). For LangGraph it means every callback
event a LangChain tracer receives: `on_chat_model_start` invocation params and metadata, plus
`on_llm_end` `llm_output` and message `response_metadata`. LangSmith and OTel exporters are built
from this same data. Raw evidence for every session (mock calls, gateway headers, trace identity
values, outputs, errors) is in `logs/exp_C_details.jsonl`.
