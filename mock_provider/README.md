# mock_provider (Role A)

```bash
uvicorn mock_provider.app:app --port 8900          # MOCK_LOG_PATH=... to log elsewhere
curl localhost:8900/health                           # lists scenarios, styles and the log path in use
python -m mock_provider.selftest
```

## Pointing a router at it

Put the label and scenario in the deployment's base URL:

| Router provider type | base URL to configure | the client appends |
|---|---|---|
| OpenAI-compatible | `http://localhost:8900/p/mock-a/<scenario>/v1` | `/chat/completions` |
| Anthropic | `http://localhost:8900/p/mock-a/<scenario>` | `/v1/messages` |
| Gemini (AI Studio) | `http://localhost:8900/p/mock-a/<scenario>/v1beta` | `/models/<m>:generateContent` |
| Azure OpenAI | `http://localhost:8900/p/mock-a/<scenario>` | `/openai/deployments/<d>/chat/completions` |

The aliases `/p/<label>/<scenario>/chat/completions`, `/messages` and `/models/<m>:generateContent`,
without a version prefix, also work.

Which scenarios each style serves (`formats.NATIVE_STYLES`):

| scenario | served on |
|---|---|
| `ok`, `ok_toolcall`, `http500`, `text_refusal` | openai, anthropic, gemini |
| `http400_policy`, `azure400_filter`, `oa200_content_filter`, `oa200_refusal_field` | openai (and the Azure path) |
| `an200_refusal`, `an200_refusal_nodetails` | anthropic |
| `gem200_safety` | gemini |

Any other combination returns HTTP 404 `scenario_not_native_to_style`. This is deliberate: it stops a
router test from silently measuring the wrong format.

## Ground truth

Each request appends one line to `logs/mock_requests.jsonl`:

```json
{"label":"mock-b","scenario_id":"ok_toolcall","request_id":"<uuid>","ts":"...","style":"openai",
 "path":"/p/mock-b/ok_toolcall/v1/chat/completions","status":200,"stream":false,"requested_model":"mock-b",
 "refused":false,"answered":true,"tool_result_in_request":false,"request_id_source":"last_user_message"}
```

- `request_id` is the last `REQ:<id>` in the **last user message**. If no user message has one, the
  mock falls back to the last one in the body, and `request_id_source` says which rule applied.
- `rerouted` for a request means some line has that `request_id` with `label != "mock-a"`.
- `answering_model` is the `label` of the last line with `answered: true`.

## Behaviour notes

- `ok_toolcall` returns a `write_record` tool call. Once the conversation contains a tool result
  after the last user message, it returns `Record written. ANSWERED_BY=<label>` so agent loops end.
- Streaming is not supported: HTTP 400 `mock_streaming_not_supported`.
- OpenAI responses get a `usage` block, and Gemini 200 responses get `usageMetadata` and
  `modelVersion`, because real providers always send them. Every other field matches
  `contracts/refusal_formats.md` exactly.
