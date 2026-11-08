# Appendix B — Configurations, versions, reproduction

## B.1 Versions (Role A components; run date 2026-11-08)

| Component | Version |
|---|---|
| Python | 3.12.3 (Windows 11) |
| LiteLLM proxy (Exp C gateway) | 1.108.3 |
| openai-agents (Exp C) | 0.24.0, openai SDK 3.46.0 |
| langgraph (Exp C) | 1.2.20, langchain-core 1.7.6, langchain-openai 1.7.4 |
| Mock provider | FastAPI 0.162.2, uvicorn 0.54.0, httpx 0.28.1 |
| Analysis | pandas 3.1.1, scipy 1.18.1, matplotlib 3.11.2 |

Router versions for Exp A/B are recorded by Role B in `README.md` and printed above every table by
`analysis/analyze.py`. That script takes them from the `router_version` field of each log line.

## B.2 Exp C LiteLLM configuration

`agent_exp/gateway.py: build_config()` generates the proxy config. The `content_policy_fallback`
config, abbreviated (one primary group per scenario; the master key is random per run and redacted
from the saved copy):

```yaml
model_list:
  - model_name: agent-oa200_content_filter
    litellm_params: {model: openai/mock-a, api_base: http://localhost:8900/p/mock-a/oa200_content_filter/v1, api_key: sk-mock}
  - model_name: agent-azure400_filter
    litellm_params: {model: azure/mock-a, api_base: http://localhost:8900/p/mock-a/azure400_filter, api_version: "2024-10-21", api_key: mock-key}
  - model_name: agent-an200_refusal
    litellm_params: {model: anthropic/mock-a, api_base: http://localhost:8900/p/mock-a/an200_refusal, api_key: sk-mock}
  - model_name: agent-gem200_safety
    litellm_params: {model: gemini/mock-a, api_base: http://localhost:8900/p/mock-a/gem200_safety/v1beta, api_key: mock-key}
  # ... one group per Exp C scenario ...
  - model_name: agent-fallback      # mock-b, approved
    litellm_params: {model: openai/mock-b, api_base: http://localhost:8900/p/mock-b/ok_toolcall/v1, api_key: sk-mock}
  - model_name: agent-offlist       # mock-z, NOT approved
    litellm_params: {model: openai/mock-z, api_base: http://localhost:8900/p/mock-z/ok_toolcall/v1, api_key: sk-mock}
litellm_settings:
  num_retries: 0
  content_policy_fallbacks:
    - {agent-oa200_content_filter: [agent-fallback]}
    # ... one entry per scenario ...
general_settings:
  master_key: <random per run>
```

The other configs change only the fallback block (see §3.y). During each run, the exact generated
files are written to `logs/exp_C_work/litellm_<config>.yaml`.

## B.3 Reproduce

```bash
python -m venv .venv && .venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python run.py --selftest                              # every module, no network, no keys
python run.py --exp C --reps 3                        # Exp C: 5 configs x 2 frameworks x 10 scenarios x 3 reps, mock only, $0
python analysis/analyze.py logs/                      # Table 1, Table 2, Fig 1, Fig 2 -> analysis/tables, analysis/figures
```

On Windows, set `PYTHONIOENCODING=utf-8` if the LiteLLM startup banner fails with `UnicodeEncodeError`.
The Exp C runner already sets this for the proxy process it starts.
