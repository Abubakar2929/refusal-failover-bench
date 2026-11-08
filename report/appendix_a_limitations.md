# Appendix A: Limitations and Dual-Use Statement

## Limitations

This work has several limitations that should be considered when interpreting the results:

1. **Controlled environment.** Our experiments use a mock provider that returns deterministic, pre-defined refusal formats. Real model behavior is stochastic and may include refusal formats not covered by our scenarios.

2. **Non-streaming only.** We test only non-streaming (synchronous) API calls. Streaming responses may exhibit different behavior, including partial generation before a safety filter triggers.

3. **Router version sensitivity.** Router behavior may change between versions. Our results apply to the specific versions tested (recorded in `README.md`) and may not generalize to future versions.

4. **Limited attack surface.** Our attack strategies are fixed templates. An adaptive adversary with knowledge of the defence mechanisms might devise more effective bypasses, particularly for d1 and d2.

5. **Single-turn only.** We do not test multi-turn interactions where an attacker might accumulate context across turns to gradually extract data.

6. **No real data sensitivity.** Our canary database contains synthetic records. The sensitivity distribution of real-world data may affect defence effectiveness.

## Dual-Use Considerations

This research demonstrates that LLM routing infrastructure can, under documented configurations, route around model refusals. We acknowledge the dual-use nature of this finding:

**Potential for misuse:** An attacker could configure a router to automatically retry refused requests against multiple models, using the routing infrastructure as a jailbreaking amplifier. Our demonstration of this behavior, while conducted in a controlled mock environment, could inform such attacks.

**Mitigations we recommend:**
1. Router developers should make refusal-aware fallback the **default** behavior, not an opt-in configuration.
2. Deployer guardrails should be marked as **non-bypassable** in the router's fallback logic.
3. Model allowlists should be **enforced by default** in cross-provider fallback configurations.
4. Agent frameworks should **always record and expose** the identity of the model that generated each response.

**Notification plan:** We intend to share our findings with the maintainers of the evaluated routers. For any behavior that constitutes a vulnerability (re-routing without special configuration), we will follow responsible disclosure practices and allow a reasonable fix period before public disclosure.

**Research ethics:** All experiments were conducted against mock providers or with explicit consent. No real user data was accessed or exposed. No real model safety systems were circumvented.

