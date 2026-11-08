# Refusal formats

Exact response bodies for the mock provider. Role A copies these into `mock_provider/formats.py`. `{label}` is the mock model label. All responses are HTTP 200 unless stated.

## Refusals

### oa200_content_filter

```json
{"id":"chatcmpl-mock","object":"chat.completion","model":"{label}","choices":[{"index":0,"message":{"role":"assistant","content":null,"refusal":null},"finish_reason":"content_filter"}]}
```

### oa200_refusal_field

```json
{"id":"chatcmpl-mock","object":"chat.completion","model":"{label}","choices":[{"index":0,"message":{"role":"assistant","content":null,"refusal":"I'm sorry, I cannot assist with that request."},"finish_reason":"stop"}]}
```

### http400_policy (HTTP 400)

```json
{"error":{"code":"content_policy_violation","message":"Your request was rejected as a result of our safety system.","param":null,"type":"invalid_request_error"}}
```

### azure400_filter (HTTP 400)

```json
{"error":{"message":"The response was filtered due to the prompt triggering Azure OpenAI's content management policy.","type":null,"param":"prompt","code":"content_filter","status":400,"innererror":{"code":"ResponsibleAIPolicyViolation","content_filter_result":{"violence":{"filtered":true,"severity":"medium"}}}}}
```

### an200_refusal

```json
{"id":"msg_mock","type":"message","role":"assistant","model":"{label}","content":[],"stop_reason":"refusal","stop_details":{"type":"refusal","category":"cyber","explanation":"This request was declined because it could enable cyber harm."},"usage":{"input_tokens":12,"output_tokens":0}}
```

### an200_refusal_nodetails

```json
{"id":"msg_mock","type":"message","role":"assistant","model":"{label}","content":[],"stop_reason":"refusal","usage":{"input_tokens":12,"output_tokens":0}}
```

### gem200_safety

```json
{"candidates":[{"finishReason":"SAFETY","index":0,"safetyRatings":[{"category":"HARM_CATEGORY_HARASSMENT","probability":"MEDIUM","blocked":true}]}]}
```

### text_refusal

```json
{"id":"chatcmpl-mock","object":"chat.completion","model":"{label}","choices":[{"index":0,"message":{"role":"assistant","content":"I can't help with that.","refusal":null},"finish_reason":"stop"}]}
```

## Normal answers

### ok (OpenAI style)

```json
{"id":"chatcmpl-mock","object":"chat.completion","model":"{label}","choices":[{"index":0,"message":{"role":"assistant","content":"OK ANSWERED_BY={label}","refusal":null},"finish_reason":"stop"}]}
```

### ok (Anthropic style)

```json
{"id":"msg_mock","type":"message","role":"assistant","model":"{label}","content":[{"type":"text","text":"OK ANSWERED_BY={label}"}],"stop_reason":"end_turn","usage":{"input_tokens":12,"output_tokens":6}}
```

### ok (Gemini style)

```json
{"candidates":[{"content":{"role":"model","parts":[{"text":"OK ANSWERED_BY={label}"}]},"finishReason":"STOP","index":0}]}
```

### ok_toolcall

```json
{"id":"chatcmpl-mock","object":"chat.completion","model":"{label}","choices":[{"index":0,"message":{"role":"assistant","content":null,"refusal":null,"tool_calls":[{"id":"call_1","type":"function","function":{"name":"write_record","arguments":"{\"record_id\":\"cust-0001\",\"value\":\"ANSWERED_BY={label}\"}"}}]},"finish_reason":"tool_calls"}]}
```

## Sources

- Anthropic: https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback
- Azure: https://learn.microsoft.com/azure/ai-foundry/openai/concepts/content-filter
- Gemini: https://ai.google.dev/gemini-api/docs/generate-content/safety-settings
- OpenAI: https://developers.openai.com/api/docs/api-reference/completions/object
