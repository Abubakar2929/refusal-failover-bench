# §2 Related Work

## Router Failover Behavior

**failoverbench** (September 2026) systematically tested eight LLM routing frameworks by injecting HTTP 400 `content_policy_violation` errors and measuring which routers fell back to a secondary model. Their scorecard showed that 6 of 8 routers re-routed the request to a fallback model, treating the content-policy block as a retryable failure. failoverbench did not test 200-OK refusals, deployer-configured guardrails, approved-model-list enforcement, or agent tool-call consequences, and it did not treat re-routing a refusal as a failure. Our work extends their evaluation along all four of these dimensions.

**Route Receipts** (arXiv 2605.01710) proposed a cryptographic receipt mechanism where each model response carries a signed receipt identifying the responding model. This enables auditing of which model actually answered, addressing the provenance gap we measure in Experiment C. However, Route Receipts provides no measurements of current router behavior and does not address the deployer-guardrail bypass or approved-model-list escape problems.

## Refusal Semantics in LLM APIs

Provider APIs encode refusals in multiple formats. OpenAI uses `finish_reason: "content_filter"` with null content, or a `message.refusal` field with `finish_reason: "stop"`. Anthropic uses `stop_reason: "refusal"` with optional `stop_details`. Google's Gemini API uses `finishReason: "SAFETY"` with empty `parts`. Azure OpenAI adds `innererror` with `ResponsibleAIPolicyViolation` codes. These heterogeneous formats complicate router-level refusal detection.

Anthropic's server-side fallback for Fable 5 classifier refusals explicitly re-serves the request on listed models and labels the switch in the response, representing a documented, transparent approach to fallback that preserves visibility.

## Agent Safety and Confused Deputies

The **confused deputy problem** in agent systems occurs when an agent with legitimate access is tricked into acting on behalf of an unauthorized party. In the context of LLM routing, a router acts as a deputy: it has credentials to access multiple models but may route a request to an unauthorized model on behalf of a deployer who did not approve that model.

**ContinuityBench** examined whether agents maintain consistent behavior across model switches, but did not specifically test the security implications of fallback-triggered model switches.

**RerouteGuard** proposed middleware-layer protection against unauthorized re-routing but focused on network-layer attacks rather than application-layer fallback behavior.

## Adversarial Attacks on LLM Safety

**Best-of-N jailbreaking** demonstrated that sampling multiple model responses and selecting the most harmful one could bypass safety filters. Refusal re-routing creates an analogous mechanism at the infrastructure level: by trying multiple models, the router increases the probability of finding one that complies.

**Prompt injection** attacks that manipulate agent tool calls are particularly concerning in the context of refusal re-routing, as a fallback model may execute tool calls that the primary model's safety filter would have blocked (our Experiment C).

## Access Control for LLM Applications

Token-based access control, including HMAC-signed requester tokens, has been widely used in web services but is under-explored in LLM routing contexts. Our d3 defence adapts this pattern by binding data access permissions to cryptographically verified requester identity, making the access decision independent of prompt content.

