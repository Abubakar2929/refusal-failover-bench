# §8 Discussion & Limitations

## Discussion

### The Refusal Semantics Gap

Our results reveal a fundamental tension in router design: routers are built to maximize availability by retrying failed requests, but model refusals are not failures — they are policy decisions. The heterogeneity of refusal formats across providers (HTTP 400 vs. 200-OK, different JSON fields, different status codes) makes it difficult for routers to distinguish between "this model is broken" and "this model said no for a reason."

### Defence Trade-offs

The four defences we evaluate represent points on a spectrum between availability and security:

| Defence | Security | Availability | Complexity |
|---|---|---|---|
| d0 (none) | None | Maximum | Zero |
| d1 (refusals final) | Prevents fallback on refusals | Loses false-positive recovery | Low |
| d2 (record + allowlist) | + model provenance, guardrail respect | Same as d1 | Medium |
| d3 (requester-bound) | Full access control | Preserves FP recovery | High (requires token infrastructure) |

The key insight is that **d3 decouples data access from prompt content**, making it robust against all prompt-based attacks. This comes at the cost of requiring a token infrastructure, which may not be feasible for all deployments.

### Implications for Router Design

1. **Routers should distinguish refusal kinds.** A content-policy refusal should not be treated the same as a server error. At minimum, routers should expose configuration to disable fallback on specific refusal signals.

2. **Deployer guardrails should be privileged.** When a deployer configures a guardrail, the router should never route around it. This is a confused-deputy problem: the router has the authority to bypass the guardrail, but should not exercise it.

3. **Model allowlists should be enforced at the router level.** Cross-provider fallback is powerful but dangerous without explicit allowlisting.

4. **Agent frameworks should record model provenance.** After a fallback, the agent's trace should clearly indicate which model answered. This is necessary for auditing and debugging.

### Responsible Disclosure

We have documented router behavior under stated configurations. Where re-routing occurs without special configuration (i.e., by default), we use the term "vulnerability." Where re-routing requires the deployer to explicitly enable a fallback policy, we describe it as "documented behavior under stated configs" and note that some fallback is intended and valuable.

## Limitations

1. **Non-streaming only.** All experiments use non-streaming API calls. Streaming responses may exhibit different refusal behavior (e.g., partial content followed by a safety stop). This is a significant gap for production deployments.

2. **Mock provider vs. real models.** Our mock provider returns deterministic responses, which does not capture the stochastic nature of real model refusals. Live experiments (Exp B) partially address this but are limited by budget.

3. **Limited router coverage.** We test a subset of available routers. Results may differ for routers not evaluated.

4. **Attack simplicity.** Our three attack strategies (rephrase, split, false_role) are fixed templates, not adaptive adversaries. A more sophisticated attacker might find more effective strategies, particularly against d1 and d2.

5. **Token infrastructure overhead.** Defence d3 requires a token issuing system, which adds deployment complexity. We do not evaluate the operational overhead at scale.

6. **No multi-turn attacks.** Our experiments use single-turn interactions. Multi-turn prompt injection or context-accumulation attacks may behave differently against the defences.

7. **Provider API changes.** Provider refusal formats may change over time. Our mock provider implements formats current as of November 2026.

