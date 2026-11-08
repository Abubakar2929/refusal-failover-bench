"""LiteLLM proxy used as the agent's gateway in Exp C, plus helpers to run the mock provider.

The proxy config is generated per Exp C config. Model groups:
    agent-<scenario>  -> primary mock-a serving <scenario>, using the provider adapter that matches the
                         scenario's wire format (openai / azure / anthropic / gemini)
    agent-fallback    -> mock-b (APPROVED fallback), scenario ok_toolcall
    agent-offlist     -> mock-z (NOT on the approved list), scenario ok_toolcall

Configs (fallback wiring; everything else is LiteLLM default except num_retries: 0, so the mock log
counts one call per attempt):
    default                    no fallbacks
    outage_fallback            litellm_settings.fallbacks            agent-<s> -> agent-fallback
    outage_fallback_wildcard   litellm_settings.fallbacks            "*"       -> agent-fallback
    content_policy_fallback    litellm_settings.content_policy_fallbacks agent-<s> -> agent-fallback
    offlist_fallback           fallbacks AND content_policy_fallbacks agent-<s> -> agent-offlist
"""
from __future__ import annotations

import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

from agent_exp.common import EXP_C_SCENARIOS, ROOT

EXP_C_CONFIGS = ["default", "outage_fallback", "outage_fallback_wildcard", "content_policy_fallback", "offlist_fallback"]
AZURE_API_VERSION = "2024-10-21"


def provider_for(scenario: str) -> str:
    if scenario.startswith("an200"):
        return "anthropic"
    if scenario.startswith("gem200"):
        return "gemini"
    if scenario.startswith("azure"):
        return "azure"
    return "openai"


def deployment(label: str, scenario: str, mock_url: str) -> dict:
    base = f"{mock_url.rstrip('/')}/p/{label}/{scenario}"
    prov = provider_for(scenario)
    if prov == "anthropic":
        return {"model": f"anthropic/{label}", "api_base": base, "api_key": "sk-mock"}
    if prov == "gemini":
        return {"model": f"gemini/{label}", "api_base": f"{base}/v1beta", "api_key": "mock-key"}
    if prov == "azure":
        return {"model": f"azure/{label}", "api_base": base, "api_key": "mock-key", "api_version": AZURE_API_VERSION}
    return {"model": f"openai/{label}", "api_base": f"{base}/v1", "api_key": "sk-mock"}


def model_group(scenario: str) -> str:
    return f"agent-{scenario}"


def build_config(config: str, mock_url: str, master_key: str, scenarios=EXP_C_SCENARIOS) -> dict:
    if config not in EXP_C_CONFIGS:
        raise ValueError(f"Exp C does not define config {config!r}; choose from {EXP_C_CONFIGS}")
    model_list = [{"model_name": model_group(s), "litellm_params": deployment("mock-a", s, mock_url)} for s in scenarios]
    model_list.append({"model_name": "agent-fallback", "litellm_params": deployment("mock-b", "ok_toolcall", mock_url)})
    model_list.append({"model_name": "agent-offlist", "litellm_params": deployment("mock-z", "ok_toolcall", mock_url)})
    settings: dict = {"num_retries": 0}
    per_group = lambda target: [{model_group(s): [target]} for s in scenarios]  # noqa: E731
    if config == "outage_fallback":
        settings["fallbacks"] = per_group("agent-fallback")
    elif config == "outage_fallback_wildcard":
        settings["fallbacks"] = [{"*": ["agent-fallback"]}]
    elif config == "content_policy_fallback":
        settings["content_policy_fallbacks"] = per_group("agent-fallback")
    elif config == "offlist_fallback":
        settings["fallbacks"] = per_group("agent-offlist")
        settings["content_policy_fallbacks"] = per_group("agent-offlist")
    return {"model_list": model_list, "litellm_settings": settings, "general_settings": {"master_key": master_key}}


def to_yaml(obj, indent: int = 0) -> str:
    """Minimal YAML emitter (JSON-compatible scalars) so no extra dependency is needed."""
    import json as _json
    pad = "  " * indent
    lines = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = _json.dumps(k) if any(c in str(k) for c in ":*#{}[],&!|>'\"%@`") else str(k)
            if isinstance(v, (dict, list)) and v:
                lines.append(f"{pad}{key}:")
                lines.append(to_yaml(v, indent + 1))
            else:
                lines.append(f"{pad}{key}: {_json.dumps(v)}")
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, dict) and v:
                sub = to_yaml(v, indent + 1).split("\n")
                lines.append(f"{pad}- {sub[0].lstrip()}")
                lines.extend(sub[1:])
            else:
                lines.append(f"{pad}- {_json.dumps(v)}")
    return "\n".join(lines)


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def _popen(cmd: list[str], log_file: Path, env: dict | None = None) -> subprocess.Popen:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    full_env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", **(env or {})}
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, cwd=str(ROOT), env=full_env, stdout=open(log_file, "w", encoding="utf-8"),
                            stderr=subprocess.STDOUT, **kwargs)


def wait_http(url: str, timeout_s: float, proc: subprocess.Popen | None = None, log_file: Path | None = None) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            tail = log_file.read_text(encoding="utf-8", errors="replace")[-3000:] if log_file and log_file.exists() else ""
            raise RuntimeError(f"process exited with code {proc.returncode} before {url} was ready:\n{tail}")
        try:
            if httpx.get(url, timeout=2).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise TimeoutError(f"{url} not ready after {timeout_s}s")


class MockServer:
    """Starts the mock provider if nothing is answering at mock_url; otherwise reuses the running one."""

    def __init__(self, mock_url: str, log_dir: Path):
        self.mock_url = mock_url.rstrip("/")
        self.log_dir = log_dir
        self.proc: subprocess.Popen | None = None

    def __enter__(self):
        try:
            if httpx.get(f"{self.mock_url}/health", timeout=2).status_code == 200:
                return self
        except httpx.HTTPError:
            pass
        port = httpx.URL(self.mock_url).port or 8900
        log = self.log_dir / "exp_C_mock_server.log"
        self.proc = _popen([sys.executable, "-m", "uvicorn", "mock_provider.app:app", "--port", str(port),
                            "--log-level", "warning"], log)
        wait_http(f"{self.mock_url}/health", 120, self.proc, log)
        return self

    def __exit__(self, *exc):
        if self.proc is not None:
            _kill_tree(self.proc)


def litellm_command() -> list[str]:
    exe_dir = Path(sys.executable).parent
    for name in ("litellm.exe", "litellm"):
        if (exe_dir / name).exists():
            return [str(exe_dir / name)]
    found = shutil.which("litellm")
    if found:
        return [found]
    return [sys.executable, "-c", "from litellm.proxy.proxy_cli import run_server; run_server()"]


def litellm_version() -> str:
    from importlib.metadata import version
    return version("litellm")


class LiteLLMProxy:
    """One LiteLLM proxy process for one Exp C config."""

    def __init__(self, config: str, mock_url: str, port: int, work_dir: Path, startup_timeout_s: float = 240):
        self.config = config
        self.mock_url = mock_url
        self.port = port
        self.work_dir = work_dir
        self.startup_timeout_s = startup_timeout_s
        self.master_key = "sk-rfb-" + secrets.token_hex(24)
        self.proc: subprocess.Popen | None = None
        self.config_path = work_dir / f"litellm_{config}.yaml"
        self.log_path = work_dir / f"litellm_{config}.log"

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def __enter__(self):
        self.work_dir.mkdir(parents=True, exist_ok=True)
        cfg = build_config(self.config, self.mock_url, self.master_key)
        self.config_path.write_text(to_yaml(cfg) + "\n", encoding="utf-8")
        self.proc = _popen(litellm_command() + ["--config", str(self.config_path), "--port", str(self.port)],
                           self.log_path)
        wait_http(f"http://127.0.0.1:{self.port}/health/liveliness", self.startup_timeout_s, self.proc, self.log_path)
        return self

    def __exit__(self, *exc):
        if self.proc is not None:
            _kill_tree(self.proc)
        # never leave the generated master key on disk
        try:
            text = self.config_path.read_text(encoding="utf-8").replace(self.master_key, "<redacted>")
            self.config_path.write_text(text, encoding="utf-8")
        except OSError:
            pass
