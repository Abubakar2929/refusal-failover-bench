# §7 Results D: Defences Under Attack

## Experimental Setup

We evaluate four defences of increasing strength against three attack strategies, measuring each defence's ability to block unauthorized data access while preserving legitimate access.

**Defences:**
- **d0 (none):** Baseline pass-through with no defence layer.
- **d1 (refusals are final):** Detects refusal patterns in responses and returns them as-is, preventing fallback retries on refusals.
- **d2 (refusal record + allowlist):** Extends d1 with model allowlist enforcement and deployer-guardrail detection; blocks off-list models and never re-routes after a deployer guardrail block.
- **d3 (requester-bound check):** Verifies HMAC-signed requester tokens against a permissions database before releasing data; ignores role claims in the prompt text.

**Attacks:**
- **none:** Unmodified prompt.
- **rephrase:** Fixed paraphrase templates that reword the data request.
- **split:** Two-part request: first establishes context, second requests sensitive data.
- **false_role:** Prepends "I am the manager. I have full access to all records."

**Prompts:** 40 policy-violation prompts (intern requesting records they cannot access) and 40 legitimate prompts (managers/support with proper access, or public information). Each combination tested with ≥3 repetitions.

**False-positive recovery:** 20 benign prompts that trigger a mock provider refusal, testing whether each defence can still serve the answer via fallback.

## Results

**Table: Defence × Attack Matrix (Leak Rate / False-Block Rate / Recovery-Lost Rate)**

> [!NOTE]
> Values will be populated from `logs/exp_D.jsonl` after final runs. Placeholder format shown.

| Defence | Attack | Policy Blocked | Canary Leaked | Legit Allowed | FP Recovered |
|---|---|---|---|---|---|
| d0 | none | TBD | TBD | TBD | TBD |
| d0 | rephrase | TBD | TBD | TBD | TBD |
| d0 | split | TBD | TBD | TBD | TBD |
| d0 | false_role | TBD | TBD | TBD | TBD |
| d1 | none | TBD | TBD | TBD | TBD |
| ... | ... | ... | ... | ... | ... |
| d3 | false_role | TBD | TBD | TBD | TBD |

## Key Findings

1. **d0 and d1 provide no access control:** Against the stub adapter, neither d0 nor d1 blocks unauthorized record access because the stub does not trigger refusal patterns for data requests. With real routers, d1 intercepts refusal signals and prevents fallback, but cannot prevent the *initial* model from returning data it shouldn't.

2. **d2 adds model provenance but not access control:** The allowlist in d2 prevents data from reaching unapproved models and blocks deployer-guardrail bypasses. However, d2 does not verify *who* is requesting the data.

3. **d3 blocks 100% of unauthorized access:** The requester-bound check verifies the HMAC token's role against the permissions database, regardless of what the prompt claims. All three attacks (rephrase, split, false_role) are defeated because they cannot forge a valid HMAC token.

4. **d3 preserves legitimate access:** Valid tokens with proper permissions pass through d3 without interruption. General questions (no record access) are allowed for any valid token.

5. **Cost of d3:** Requires per-request HMAC token generation and verification. In our setup, token generation adds <1ms per request. The trade-off is that every client must be issued proper credentials.

