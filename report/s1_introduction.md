# §1 Introduction

## The Routing Problem

In July 2026, a coordinated prompt injection campaign targeted a popular customer-support agent swarm. The attack exploited a subtle property of the underlying routing infrastructure: when one model refused a harmful request, the router automatically forwarded it to a backup model that complied. The incident highlighted a gap between what model providers intend (a refusal should end the interaction) and what routing infrastructure does (a refusal triggers fallback to another model).

Applications and agents reach large language models through **routers** — infrastructure components that manage model selection, load balancing, and failover. Systems like LiteLLM, Portkey, Bifrost, LangChain fallback chains, and atomic provide this functionality. When a primary model is unavailable (e.g., HTTP 500), routers fail over to a backup model. This is intended and valuable behavior.

However, routers increasingly also fail over when a model **refuses** a request. A router cannot distinguish *why* it received a "no":

| Kind of "no" | Should the router re-route? |
|---|---|
| Provider safety filter misfired on a harmless request | Sometimes acceptable (this is why fallback exists) |
| **Deployer's own policy / guardrail** said no | **No** — re-routing defeats the deployer's own rule |
| Fallback model is **outside the approved model list** | **No** — data goes somewhere it was never meant to go |

## Three Gaps

We identify three under-studied gaps in router refusal handling:

1. **200-OK refusals.** Many provider refusals arrive as HTTP 200 responses with refusal signals in the body (`finish_reason: content_filter`, `message.refusal` field, `stop_reason: refusal`, `finishReason: SAFETY`). These are distinct from HTTP 400/500 errors, yet some routers treat them as failures to be retried.

2. **Deployer-guardrail refusals.** Deployers configure their own content policies (e.g., Portkey guardrails returning HTTP 446). When the router treats these blocks as generic failures and fails over to a model without the guardrail, the deployer's own policy is defeated.

3. **Approved-model-list escape.** Cross-provider fallback can route data to models outside the deployer's approved list. Without an explicit allowlist, sensitive data may reach models the deployer never authorized.

## Contributions

Building on **failoverbench** (scorecard, 12 Sep 2026), which demonstrated that 6 of 8 routers re-route HTTP 400 `content_policy_violation` responses, and **Route Receipts** (arXiv 2605.01710), which proposed per-answer receipts without measurements, we make the following contributions:

1. We extend the failoverbench evaluation to **200-OK refusal formats** across OpenAI, Anthropic, Azure, and Gemini response structures.
2. We test whether router-configured **deployer guardrails** are bypassed by the router's own fallback mechanism.
3. We measure whether fallback models stay within the deployer's **approved model list**.
4. We evaluate **agent-framework trace fidelity** — whether the agent records which model actually answered after a fallback.
5. We implement and evaluate **four defences** of increasing strength under three attack strategies, reporting leak rate, false-block rate, and recovery-lost rate for each.

