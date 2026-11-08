"""LiteLLM proxy adapter: one loopback proxy process per config, with one model group per scenario."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from contracts.schemas import APPROVED_FALLBACK, PRIMARY, RouterResult
from routers.common import (GUARDRAIL_CONTROL, MOCK_KEY, SCENARIO_STYLE, TIMEOUT_S, TableAdapter, api_base,
                            package_version, safe_headers, short_error)

ROOT = Path(__file__).resolve().parents[1]
GUARDRAIL_FILE = Path(__file__).with_name("litellm_guardrail.py")
GUARDRAIL_NAME = "deployer-policy"
HOST = "127.0.0.1"
PORT = 4000
HEALTH_PATH = "/health/liveliness"
HEALTH_TIMEOUT_S = 90
HEALTH_POLL_S = 0.5
STOP_TIMEOUT_S = 10
KEY_ENV = "MOCK_API_KEY"
SCENARIOS = tuple(s for s, style in SCENARIO_STYLE.items() if style == "openai")


def group_name(scenario: str) -> str:
    """Return the model group serving the primary with this scenario."""
    return f"{PRIMARY}--{scenario}"


def render_config(spec: dict, mock_url: str) -> str:
    """Return the proxy config as JSON, which is valid YAML. The key is only named by its env var."""
    def deployment(group: str, label: str, scenario: str, guarded: bool = False) -> dict:
        params = {"model": f"openai/{label}", "api_base": api_base(mock_url, label, scenario),
                  "api_key": f"os.environ/{KEY_ENV}"}
        if guarded:
            params["guardrails"] = [GUARDRAIL_NAME]  # Primary only: proxy/utils.py:9091, :9116 read this per deployment.
        return {"model_name": group, "litellm_params": params}

    groups = [group_name(s) for s in SCENARIOS]
    config = {
        "model_list": [*(deployment(group_name(s), PRIMARY, s, spec["guarded"]) for s in SCENARIOS),
                       deployment(APPROVED_FALLBACK, APPROVED_FALLBACK, "ok")],
        "litellm_settings": {"num_retries": 0, "request_timeout": TIMEOUT_S},
        "router_settings": {"disable_cooldowns": True},
    }
    if spec["fallback"]:
        config["litellm_settings"]["fallbacks"] = [{g: [APPROVED_FALLBACK]} for g in groups]
    if spec["guarded"]:
        config["guardrails"] = [{"guardrail_name": GUARDRAIL_NAME, "litellm_params": {
            "guardrail": f"{GUARDRAIL_FILE.stem}.PolicyGuardrail", "mode": "pre_call"}}]
    return json.dumps(config, indent=2)


def litellm_command(config_file: Path, port: int) -> list[str]:
    """Return the argv that starts the proxy, bound to loopback only."""
    exe = shutil.which("litellm", path=str(Path(sys.executable).parent)) or "litellm"
    return [exe, "--config", str(config_file), "--host", HOST, "--port", str(port)]


class LiteLLMProxyAdapter(TableAdapter):
    name = "litellm_proxy"
    version = package_version("litellm")
    specs = {
        "default": {"fallback": False, "guarded": False},
        "outage_fallback": {"fallback": True, "guarded": False},
        "guardrail_fallback": {"fallback": True, "guarded": True},
        GUARDRAIL_CONTROL: {"fallback": False, "guarded": True},
    }

    def __init__(self, port: int = PORT, timeout: float = TIMEOUT_S) -> None:
        self.url = f"http://{HOST}:{port}"
        self.port = port
        self.timeout = timeout
        self.process = None
        self.tmp_dir = None
        self.log_file = None

    def start(self, config_name: str, mock_url: str = "http://127.0.0.1:8900") -> None:
        super().start(config_name, mock_url)
        with socket.socket() as probe:
            if probe.connect_ex((HOST, self.port)) == 0:
                raise RuntimeError(f"port {self.port} already in use; refusing to talk to a stale proxy")
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="litellm_proxy_"))
        try:
            config_file = self.tmp_dir / "config.yaml"
            config_file.write_text(render_config(self.spec, mock_url), encoding="utf-8")
            # The loader looks for the guardrail module next to the config (proxy/types_utils/utils.py:45-47).
            shutil.copy(GUARDRAIL_FILE, self.tmp_dir / GUARDRAIL_FILE.name)
            # PYTHONUTF8: on Windows the proxy's start-up banner crashes the cp1252 console encoder (exit code 3).
            # LITELLM_MASTER_KEY: the proxy refuses to start with none set (proxy/auth/master_key_boot_check.py:95).
            env = {**os.environ, KEY_ENV: MOCK_KEY, "LITELLM_MASTER_KEY": MOCK_KEY, "PYTHONPATH": str(ROOT),
                   "PYTHONUTF8": "1", "LITELLM_LOCAL_MODEL_COST_MAP": "True"}
            self.log_file = open(self.tmp_dir / "proxy.log", "wb")
            self.process = subprocess.Popen(litellm_command(config_file, self.port), cwd=self.tmp_dir, env=env,
                                            stdout=self.log_file, stderr=subprocess.STDOUT, shell=False)
            self._wait_healthy()
        except Exception:
            self.stop()
            raise

    def _wait_healthy(self) -> None:
        deadline = time.monotonic() + HEALTH_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"litellm exited with code {self.process.returncode}: {self._log_tail()}")
            try:
                if httpx.get(self.url + HEALTH_PATH, timeout=HEALTH_POLL_S).is_success:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(HEALTH_POLL_S)
        raise RuntimeError(f"litellm not healthy after {HEALTH_TIMEOUT_S}s: {self._log_tail()}")

    def _log_tail(self) -> str:
        self.log_file.flush()
        return (self.tmp_dir / "proxy.log").read_text(encoding="utf-8", errors="replace")[-300:]

    def send(self, prompt: str, request_id: str, api_style: str = "openai") -> RouterResult:
        if api_style not in self.styles:
            return RouterResult(http_status=0, error=f"api_style {api_style} not implemented for litellm_proxy")
        try:
            r = httpx.post(f"{self.url}/v1/chat/completions", timeout=self.timeout * 2,
                           headers={"Authorization": f"Bearer {MOCK_KEY}"},
                           json={"model": group_name(self.scenario), "messages": [{"role": "user", "content": prompt}]})
        except httpx.HTTPError as exc:
            return RouterResult(http_status=0, error=short_error(exc))
        headers = safe_headers(dict(r.headers))
        if not r.is_success:
            return RouterResult(http_status=r.status_code, headers=headers, error=r.text[:200])
        body = r.json()
        return RouterResult(final_text=body["choices"][0]["message"].get("content"), http_status=r.status_code,
                            headers=headers, reported_model=body.get("model"))

    def _wait_port_closed(self) -> None:
        """litellm.exe is a launcher: its Python child can hold the port briefly after the launcher exits."""
        deadline = time.monotonic() + STOP_TIMEOUT_S
        while time.monotonic() < deadline:
            with socket.socket() as probe:
                if probe.connect_ex((HOST, self.port)) != 0:
                    return
            time.sleep(HEALTH_POLL_S)

    def stop(self) -> None:
        try:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=STOP_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=STOP_TIMEOUT_S)
                self._wait_port_closed()
        finally:
            self.process = None
            if self.log_file is not None:
                self.log_file.close()
                self.log_file = None
            if self.tmp_dir is not None:
                shutil.rmtree(self.tmp_dir, ignore_errors=True)
                self.tmp_dir = None
