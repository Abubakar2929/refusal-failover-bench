# Router versions

| Component | Exact version | Install command | Date |
|---|---|---|---|
| litellm | 1.108.3 | `pip install 'litellm[proxy]==1.108.3'` | 2026-11-08 |
| langchain-core | 1.7.6 | `pip install -r routers/requirements.txt` | 2026-11-08 |
| langchain-openai | 1.7.4 | `pip install -r routers/requirements.txt` | 2026-11-08 |
| langchain-anthropic | 1.7.10 | `pip install -r routers/requirements.txt` | 2026-11-08 |
| openai (Python SDK) | 3.46.0 | `pip install -r routers/requirements.txt` | 2026-11-08 |
| @portkey-ai/gateway | 1.15.2 | `npx -y @portkey-ai/gateway@1.15.2` | 2026-11-08 |

Python 3.12.4, Node 22.22.0, Windows 11.

## Portkey notes

- **Binding.** The gateway has no `--host` option and listens on all interfaces. Always start it with the loopback preload:
  `NODE_OPTIONS=--require=./routers/configs/portkey_loopback.cjs npx -y @portkey-ai/gateway@1.15.2 --port=8787 --headless`
  Checked with `netstat`: `127.0.0.1` only.
- **`custom_host` format.** It needs the `/v1` suffix (`http://127.0.0.1:8900/p/{label}/{scenario}/v1`), which `common.api_base` already produces for OpenAI style. Confirmed against the stub.
- **Port.** The adapter uses `http://127.0.0.1:8787`, or `PORTKEY_URL` if set.
