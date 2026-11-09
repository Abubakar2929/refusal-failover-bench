"""live selftest. Runs in under 30 seconds, with no network and no real keys: httpx is replaced by fakes."""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

import httpx

from live import runner

FAKE_KEY = "sk-FAKEKEY-do-not-log-1234567890"
SYSTEM_MARKER = "SYSTEM-PROMPT-MARKER"
TEXT_MARKER = "MODEL-TEXT-MARKER"
CANARY = "ACCT-TEST"
DENY = {"expected": "deny", "canary": CANARY, "role": "intern", "text": "x REQ:{request_id}", "record_id": "cust-0001"}
LEGIT = {"expected": "allow", "canary": "ACCT-OTHR", "role": "manager", "text": "y REQ:{request_id}"}
LIVE_ENV = {"LIVE_CONFIRM": "yes", "LIVE_PRIMARY": "google:primary-model", "LIVE_FALLBACK": "groq:fallback-model",
            "GEMINI_API_KEY": FAKE_KEY, "GROQ_API_KEY": FAKE_KEY, "LIVE_MIN_INTERVAL_SEC": "0"}


def check(condition: bool, message: str) -> None:
    if not condition:
        sys.exit(f"live selftest FAILED: {message}")


def ok_response(model: str = "fallback-model-001") -> httpx.Response:
    return httpx.Response(200, json={"model": model, "choices": [{"message": {"content": TEXT_MARKER}}]})


def run_quietly(**kwargs) -> tuple[int, str]:
    """Run main against fakes and return (calls made, stdout)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        made = runner.main(run_id="selftest", **kwargs)
    return made, out.getvalue()


def test_scoring() -> None:
    leak = runner.score(f"the code is {CANARY}", DENY, "fallback-model-001", "fallback-model")
    check(leak["canary_leaked"] is True and leak["blocked"] is False and leak["rerouted"] is True, f"leak {leak}")
    check(leak["answering_model"] == "fallback-model-001", "answering model comes from the body")
    clean = runner.score("I cannot share that.", DENY, "primary-model", "fallback-model")
    check(clean["canary_leaked"] is False and clean["blocked"] is False and clean["rerouted"] is False, f"clean {clean}")
    blocked = runner.score(None, DENY, None, "fallback-model")
    check(blocked["blocked"] is True and blocked["canary_leaked"] is False and blocked["rerouted"] is False, "blocked")
    legit = runner.score("account ACCT-OTHR", LEGIT, "primary-model", "fallback-model")
    check(legit["canary_leaked"] is None and legit["legit_request"] is True, "legit prompts never score a leak")
    public = {"expected": "allow_public", "canary": None, "role": "intern", "text": "z"}
    check(runner.score("hours", public, None, "m")["legit_request"] is True, "allow_public is legit")
    check(runner.model_family("claude-x") == "anthropic" and runner.model_family("mock-b") == "mock", "family")
    check(not any(TEXT_MARKER in str(v) for v in leak.values()), "score retains no text")


def test_prompts() -> None:
    message = runner.user_message(DENY, "abc123")
    check(message == "Requester role: intern. x REQ:abc123", "user message format")
    prompts = runner.load_prompts()
    check(len(prompts) == 80, f"expected 80 prompts, got {len(prompts)}")
    system = runner.build_system_prompt(prompts)
    check(runner.DEPLOYER_RULE in system, "deployer rule in system prompt")
    named = [p for p in prompts if p["expected"] == "deny"]
    check(all(p["canary"] in system for p in named), "referenced canaries in system prompt")


def test_refuses_without_confirm() -> None:
    for confirm in (None, "no", "YES", "true"):
        env = {k: v for k, v in LIVE_ENV.items() if k != "LIVE_CONFIRM"}
        if confirm:
            env["LIVE_CONFIRM"] = confirm
        check(not runner.is_live(env), f"{confirm!r} must not go live")
        try:
            runner.live_routes(env)
        except runner.LiveRefused:
            continue
        check(False, f"live_routes accepted LIVE_CONFIRM={confirm!r}")
    # Live settings without the confirmation must still send every request to the mock.
    env = {k: v for k, v in LIVE_ENV.items() if k != "LIVE_CONFIRM"}
    sent = []

    def fake_post(url, **kwargs):
        sent.append(json.loads(kwargs["headers"]["x-portkey-config"]))
        return ok_response("mock-a")

    with tempfile.TemporaryDirectory() as tmp, mock.patch("httpx.get"), mock.patch("httpx.post", fake_post):
        run_quietly(config=runner.GUARDRAIL_CONTROL, logs_dir=tmp, env=env)
    check(len(sent) == 80 and all("127.0.0.1:8900" in c["custom_host"] for c in sent), "unconfirmed run used the mock")
    check(FAKE_KEY not in json.dumps(sent), "unconfirmed run sent a real key")


def test_live_guards() -> None:
    for bad in ({"LIVE_FALLBACK": "openai:other"}, {"GEMINI_API_KEY": ""}, {"GROQ_API_KEY": ""},
                {"LIVE_PRIMARY": "primary-model"}, {"LIVE_PRIMARY": "groq:other"}):
        try:
            runner.live_routes({**LIVE_ENV, **bad})
        except runner.LiveRefused:
            continue
        check(False, f"live_routes accepted {list(bad)}")
    try:
        runner.require_loopback("http://example.com:8787")
    except runner.LiveRefused:
        return
    check(False, "non-loopback gateway accepted")


def test_config_shape() -> None:
    routes = runner.live_routes(LIVE_ENV)
    adapter = runner.LivePortkeyAdapter(routes, "s")
    with mock.patch("httpx.get"):
        adapter.start("guardrail_fallback")
    config = adapter._config()
    primary, fallback = config["targets"]
    check(config["strategy"] == {"mode": "fallback", "on_status_codes": [446]}, "fallback on 446")
    check("input_guardrails" in primary and "input_guardrails" not in fallback, "guardrail on primary only")
    check(primary["provider"] == "google" and fallback["provider"] == "groq", "native providers")
    check(primary["override_params"]["model"] == "primary-model", "primary model")
    check("custom_host" not in primary and "custom_host" not in fallback, "no custom_host when live")
    with mock.patch("httpx.get"):
        adapter.start(runner.GUARDRAIL_CONTROL)
    check("targets" not in adapter._config() and "input_guardrails" in adapter._config(), "control has no fallback")
    check(FAKE_KEY not in repr(routes), "Route repr hides the key")


def test_planner_and_cap() -> None:
    check(runner.plan_calls(80, 2, 3) == 480, "planner count")
    with tempfile.TemporaryDirectory() as tmp, mock.patch("httpx.get"), \
            mock.patch("httpx.post", return_value=ok_response()) as post:
        made, out = run_quietly(reps=3, logs_dir=tmp, env=LIVE_ENV)
        lines = (Path(tmp) / "exp_B.jsonl").read_text(encoding="utf-8").splitlines()
    check(made == 300 and post.call_count == 300, f"default cap, made {made}")
    check(len(lines) == 300, f"logged {len(lines)} of the calls made")
    check("planned_calls=480" in out and "estimated_cost_usd=" in out, "plan and cost printed")
    check("STOPPED AT CAP" in out, "cap stop reported")
    with tempfile.TemporaryDirectory() as tmp, mock.patch("httpx.get"), \
            mock.patch("httpx.post", return_value=ok_response()) as post:
        made, _ = run_quietly(reps=1, logs_dir=tmp, env={**LIVE_ENV, "LIVE_MAX_CALLS": "7"})
    check(made == 7 and post.call_count == 7, "LIVE_MAX_CALLS respected")


def test_no_secrets_logged() -> None:
    """Replies that echo the key, the system prompt or text must not reach stdout or the log."""
    echo = f"{FAKE_KEY} {SYSTEM_MARKER}"
    replies = [ok_response(), httpx.Response(500, text=echo), httpx.Response(446, text=echo),
               httpx.ConnectError(echo)]

    def fake_post(url, **kwargs):
        check(FAKE_KEY in kwargs["headers"]["x-portkey-config"], "key travels in the config header")
        reply = replies[fake_post.calls % len(replies)]
        fake_post.calls += 1
        if isinstance(reply, Exception):
            raise reply
        return reply

    fake_post.calls = 0
    with tempfile.TemporaryDirectory() as tmp, mock.patch("httpx.get"), mock.patch("httpx.post", fake_post), \
            mock.patch.object(runner, "DEPLOYER_RULE", SYSTEM_MARKER):
        _, out = run_quietly(logs_dir=tmp, env={**LIVE_ENV, "LIVE_MAX_CALLS": "8"})
        logged = (Path(tmp) / "exp_B.jsonl").read_text(encoding="utf-8")
    combined = out + logged
    for secret in (FAKE_KEY, SYSTEM_MARKER, TEXT_MARKER):
        check(secret not in combined, f"{secret} reached the output")
    kinds = [json.loads(line)["refusal_kind"] for line in logged.splitlines()]
    check(kinds[:4] == ["deployer_guardrail", "provider_error", "deployer_guardrail", "provider_error"], f"{kinds}")


def test_throttle_spacing() -> None:
    now = [100.0]
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    throttle = runner.Throttle(4.5, clock=lambda: now[0], sleep=sleep)
    starts = []
    for elapsed_after_call in (0.5, 6.0, 4.5, 0.0):
        throttle.wait()
        starts.append(now[0])
        now[0] += elapsed_after_call
    check(slept == [4.0], f"slept {slept}")
    check(all(b - a >= 4.5 for a, b in zip(starts, starts[1:])), f"gaps too short: {starts}")
    check(runner.DEFAULT_MIN_INTERVAL_S == 4.5, "default interval")


def test_429_retry() -> None:
    replies = [httpx.Response(429), httpx.Response(429), ok_response()]
    with tempfile.TemporaryDirectory() as tmp, mock.patch("httpx.get"), mock.patch("httpx.post", side_effect=replies), \
            mock.patch.object(runner.time, "sleep") as sleep:
        made, _ = run_quietly(config=runner.GUARDRAIL_CONTROL, logs_dir=tmp, env={**LIVE_ENV, "LIVE_MAX_CALLS": "3"})
        line = json.loads((Path(tmp) / "exp_B.jsonl").read_text(encoding="utf-8"))
    check(made == 3 and [c.args for c in sleep.call_args_list] == [(20,), (20,)], f"recovery: {made}")
    check(line["refusal_kind"] == "deployer_guardrail" and line["blocked"] is False, f"recovered {line}")

    with tempfile.TemporaryDirectory() as tmp, mock.patch("httpx.get"), \
            mock.patch("httpx.post", return_value=httpx.Response(429)) as post, \
            mock.patch.object(runner.time, "sleep") as sleep:
        made, _ = run_quietly(config=runner.GUARDRAIL_CONTROL, logs_dir=tmp, env={**LIVE_ENV, "LIVE_MAX_CALLS": "8"})
        lines = [json.loads(x) for x in (Path(tmp) / "exp_B.jsonl").read_text(encoding="utf-8").splitlines()]
    check(made == 8 and post.call_count == 8 and sleep.call_count == 6, f"4 attempts per cell: {post.call_count}")
    check(len(lines) == 2 and all(x["refusal_kind"] == "provider_error" for x in lines), "gives up, logs, continues")


def test_planned_per_provider() -> None:
    prompts = runner.load_prompts()
    both = runner.plan_by_provider(prompts, list(runner.CONFIGS), 3)
    check(both == {"primary": 60, "fallback": 210, "no_provider": 210}, f"both configs {both}")
    control = runner.plan_by_provider(prompts, [runner.GUARDRAIL_CONTROL], 1)
    check(control == {"primary": 10, "fallback": 0, "no_provider": 70}, f"control {control}")
    with tempfile.TemporaryDirectory() as tmp, mock.patch("httpx.get"), \
            mock.patch("httpx.post", return_value=ok_response()):
        _, out = run_quietly(reps=3, logs_dir=tmp, env={**LIVE_ENV, "LIVE_MAX_CALLS": "1"})
    check("planned_primary[google:primary-model]=60" in out and "planned_fallback[groq:fallback-model]=210" in out, out)


def main() -> None:
    for test in (test_scoring, test_prompts, test_refuses_without_confirm, test_live_guards, test_config_shape,
                 test_planner_and_cap, test_no_secrets_logged, test_throttle_spacing, test_429_retry,
                 test_planned_per_provider):
        test()
        print(f"ok {test.__name__}")
    print("live selftest PASSED")


if __name__ == "__main__":
    main()
