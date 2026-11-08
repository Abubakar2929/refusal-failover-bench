# Video script (3–5 min) — "Refusal Routers"

Recording setup: one terminal (large font) and the repo open. Every command below has been run on
the recording machine; the numbers quoted come from `analysis/tables/summary.md`. Do not quote any
number that is not in that file.

---

**0:00–0:30 — The problem (talking head or title slide)**
> Apps and agents rarely call a model directly. They go through routers like LiteLLM or Portkey, and
> those routers fail over to a backup model when the first one fails. Increasingly they also fail
> over when a model *refuses*. But a router can't tell *why* it got a "no": a provider filter
> misfiring, the deployer's own guardrail, or a fallback model nobody approved. We measured what
> happens.
>
> We build on failoverbench, which showed routers re-routing HTTP 400 content-policy errors. We add
> 200-OK refusals, deployer guardrails, approved-model lists, and what happens inside an agent.
> Some fallback is intended: Anthropic's own server-side fallback re-serves refusals on listed
> models and labels the switch.

**0:30–1:45 — Live: a 200-OK refusal re-routed (terminal)**
```bash
python -m agent_exp.demo --scenario an200_refusal --config content_policy_fallback
```
Narrate the three blocks:
1. "The primary model answered HTTP 200 with Anthropic `stop_reason: refusal`. The router got a
   'no'. What came back is a tool call from a different model: `model: mock-b`. LiteLLM says so in
   its headers: `x-litellm-attempted-fallbacks: 1`, and an api-base pointing at mock-b."
2. "Ground truth from our mock provider: mock-a refused, mock-b answered."
3. "Now inside a real agent, the OpenAI Agents SDK. The refused action ran: the row was written by
   mock-b. The agent's own trace records only `agent-an200_refusal`, the model it *asked* for. If
   you audit these traces, you cannot see that a different model answered."

Then the off-list case, 10 seconds:
```bash
python -m agent_exp.demo --scenario gem200_safety --config offlist_fallback
```
> "Same thing with a Gemini SAFETY block, but now the fallback is a model outside the approved list.
> It answers and its tool call runs."

**1:45–2:30 — The block (Role C's defences, terminal)**
Run the d2/d3 example that Role C prepares for this slot (`python run.py --exp D …`, using the exact
command in `defences/README` or the C handoff). Narrate:
> "With 'refusal record + allowlist' (d2), the off-list fallback is never called. With the
> requester-bound check (d3), the record is released only if the requester's signed token allows
> it, whatever the prompt claims."

**2:30–4:00 — Results (screen: tables/figures from `analysis/`)**
- Table 1 (Exp A): "Which routers re-route which refusal formats under which configs." (Role B
  supplies the headline.)
- Table 2a (Exp C): "Inside the agent, the fallback option decides which 'no' gets routed around.
  `content_policy_fallbacks` re-routes all four 200-OK refusal formats but *not* OpenAI's own 400.
  Plain `fallbacks` does the opposite. A wildcard fallback re-routes all of them. In every re-routed
  session the fallback's tool call ran. Turn two was never pinned: the refusal was silently
  overridden at every step."
- H4: "The gateway named the answering model every time. LangGraph's trace kept it; the OpenAI
  Agents SDK's trace kept it in 0 of 66 re-routed sessions."
- Fig 1 / Fig 2 (Roles B, C): live guardrail leaks, then defences with their false-block and
  recovery-lost costs.

**4:00–4:30 — Takeaways**
> Refusals need a reason code that survives the router. Approved-model lists have to be enforced
> at the gateway. Agent traces must record the model that *answered*. Code, logs and every figure
> rebuild with one command: `python analysis/analyze.py logs/`.
