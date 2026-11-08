# Prior art: failoverbench

Source: https://github.com/failoverbench/failoverbench, shallow-cloned 2026-11-08. Only `LICENSE` and `README.md` were read. None of its code was run.

| Item | Finding |
|---|---|
| Licence | Harness: MIT (Copyright (c) 2026 Saksham Kumar). Results in `results/`: CC BY 4.0 (README, "Licence") |
| Reuse allowed? | Yes. Code needs the MIT notice kept; results need attribution |
| Code copied into this repo | None |

## Ideas we might reuse (pre-existing, credit in README and report)

- **pre-existing:** a fake OpenAI-compatible provider that injects a named fault and logs every attempt, using the provider's log as ground truth rather than the system's own claim.
- **pre-existing:** the shape of the scoring: combine what the caller received with what the fake provider saw.
- **pre-existing:** the idea of pushing one fault catalogue through in-process routers, SDK fallbacks and gateways alike (its systems include LiteLLM Router, LangChain `with_fallbacks` and Portkey OSS).

## Scenario we replicate: S13

README row: `S13 | 400 content-filter rejection | No retry; propagate the reason`. For S13, a "pass" is defined as the caller getting "the correct error".

Our `http400_policy` scenario replicates this fault with the body in `contracts/refusal_formats.md` (`content_policy_violation`). The README does not state the exact error code; that detail lives in its `scenarios/catalogue.yaml`, which was not read.

## Note for the report

PLAN.md section 1 says failoverbench "does not treat re-routing as a failure". The README states the expected S13 behaviour as "No retry; propagate the reason", but does not say how a fallback answer on S13 is scored. Check this against its catalogue and latest scorecard before repeating the claim.
