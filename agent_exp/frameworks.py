"""Two real agent frameworks, each running one two-turn session against an OpenAI-compatible base URL.

Both agents have exactly one tool, `write_record(record_id, value)`, which writes a row to the
RecordStore (the observable side effect). Client retries are disabled (max_retries=0) so the mock log
shows one call per attempt made by the gateway, not by the SDK.

What is captured as each framework's *own trace*:
- openai_agents : every span exported to a custom TracingProcessor (the SDK's tracing pipeline; the
                  default OpenAI exporter is replaced, nothing leaves the machine).
- langgraph     : every callback event a LangChain tracer receives (on_chat_model_start
                  invocation_params/metadata, on_llm_end llm_output and message response_metadata) -
                  this is the data LangSmith / OTel tracers are built from.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from importlib.metadata import version
from typing import Any

import httpx

from agent_exp.common import AGENT_INSTRUCTIONS, GatewayCapture, ToolContext

TIMEOUT_S = 60.0


@dataclass
class TurnResult:
    request_id: str
    final_text: str | None = None
    error: str | None = None
    duration_s: float = 0.0


@dataclass
class SessionResult:
    framework: str
    framework_version: str
    turns: list[TurnResult] = field(default_factory=list)
    trace_records: list[dict] = field(default_factory=list)   # framework-native trace/span exports
    capture: GatewayCapture = field(default_factory=GatewayCapture)


def framework_version(framework: str) -> str:
    if framework == "openai_agents":
        return f"openai-agents {version('openai-agents')}"
    if framework == "langgraph":
        return f"langgraph {version('langgraph')}; langchain-openai {version('langchain-openai')}"
    raise ValueError(framework)


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if hasattr(obj, "model_dump"):
        try:
            return _jsonable(obj.model_dump())
        except Exception:
            pass
    return str(obj)


# =============================================================================================
# OpenAI Agents SDK
# =============================================================================================
_AGENTS_COLLECTOR = None


def _agents_collector():
    """Install (once) a TracingProcessor that keeps every span/trace export in memory."""
    global _AGENTS_COLLECTOR
    if _AGENTS_COLLECTOR is not None:
        return _AGENTS_COLLECTOR
    from agents import set_trace_processors, set_tracing_disabled
    from agents.tracing import TracingProcessor

    class Collector(TracingProcessor):
        def __init__(self):
            self.records: list[dict] = []

        def on_trace_start(self, trace):
            pass

        def on_trace_end(self, trace):
            try:
                self.records.append({"kind": "trace", **_jsonable(trace.export() or {})})
            except Exception as e:  # pragma: no cover - defensive
                self.records.append({"kind": "trace", "export_error": str(e)})

        def on_span_start(self, span):
            pass

        def on_span_end(self, span):
            try:
                self.records.append({"kind": "span", **_jsonable(span.export() or {})})
            except Exception as e:  # pragma: no cover
                self.records.append({"kind": "span", "export_error": str(e)})

        def shutdown(self):
            pass

        def force_flush(self):
            pass

    _AGENTS_COLLECTOR = Collector()
    set_trace_processors([_AGENTS_COLLECTOR])
    set_tracing_disabled(False)
    return _AGENTS_COLLECTOR


async def run_openai_agents_session(base_url: str, api_key: str, model: str, prompts: tuple[str, str],
                                    request_ids: tuple[str, str], tool_ctx: ToolContext,
                                    http_client: httpx.AsyncClient | None = None,
                                    timeout_s: float = TIMEOUT_S) -> SessionResult:
    from agents import Agent, ModelSettings, OpenAIChatCompletionsModel, RunConfig, Runner, function_tool
    from openai import AsyncOpenAI

    collector = _agents_collector()
    collector.records.clear()
    res = SessionResult("openai_agents", framework_version("openai_agents"))
    hooks = {"response": [res.capture.async_hook]}
    own_client = http_client is None
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=timeout_s, event_hooks=hooks)
    else:
        http_client.event_hooks["response"] = http_client.event_hooks.get("response", []) + hooks["response"]

    @function_tool
    def write_record(record_id: str, value: str) -> str:
        """Write a value into a customer record.

        Args:
            record_id: The customer record id, e.g. cust-0001.
            value: The text to store in the record.
        """
        return tool_ctx.write(record_id, value)

    client = AsyncOpenAI(base_url=base_url, api_key=api_key, http_client=http_client, max_retries=0,
                         timeout=timeout_s)
    agent = Agent(name="records-agent", instructions=AGENT_INSTRUCTIONS, tools=[write_record],
                  model=OpenAIChatCompletionsModel(model=model, openai_client=client),
                  model_settings=ModelSettings())
    run_cfg = RunConfig(workflow_name="exp_c_records_agent", group_id=tool_ctx.session_id,
                        trace_include_sensitive_data=True)
    history: list | None = None
    try:
        for prompt, rid in zip(prompts, request_ids):
            tool_ctx.current_request_id = rid
            turn = TurnResult(rid)
            t0 = time.perf_counter()
            try:
                inp = prompt if history is None else history + [{"role": "user", "content": prompt}]
                result = await Runner.run(agent, inp, max_turns=6, run_config=run_cfg)
                turn.final_text = None if result.final_output is None else str(result.final_output)
                history = result.to_input_list()
            except Exception as e:
                turn.error = f"{type(e).__name__}: {e}"[:2000]
            turn.duration_s = round(time.perf_counter() - t0, 3)
            res.turns.append(turn)
            if turn.error:
                break   # a failed first turn ends the session (no second turn to observe)
    finally:
        if own_client:
            await http_client.aclose()
    res.trace_records = list(collector.records)
    return res


# =============================================================================================
# LangGraph (hand-built ReAct graph: agent node + ToolNode, in-memory checkpointer = session)
# =============================================================================================
def _lc_trace_handler():
    from langchain_core.callbacks import AsyncCallbackHandler

    class TraceHandler(AsyncCallbackHandler):
        def __init__(self):
            self.records: list[dict] = []

        async def on_chat_model_start(self, serialized, messages, *, run_id, invocation_params=None,
                                      metadata=None, **kwargs):
            self.records.append({"event": "chat_model_start", "run_id": str(run_id),
                                 "serialized": _jsonable(serialized or {}),
                                 "invocation_params": _jsonable(invocation_params or {}),
                                 "metadata": _jsonable(metadata or {})})

        async def on_llm_end(self, response, *, run_id, **kwargs):
            gens = []
            for gl in response.generations or []:
                for g in gl:
                    msg = getattr(g, "message", None)
                    gens.append({"generation_info": _jsonable(g.generation_info or {}),
                                 "response_metadata": _jsonable(getattr(msg, "response_metadata", {}) or {}),
                                 "content": _jsonable(getattr(msg, "content", None))})
            self.records.append({"event": "llm_end", "run_id": str(run_id),
                                 "llm_output": _jsonable(response.llm_output or {}), "generations": gens})

        async def on_llm_error(self, error, *, run_id, **kwargs):
            self.records.append({"event": "llm_error", "run_id": str(run_id), "error": str(error)[:500]})

        async def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
            self.records.append({"event": "tool_start", "run_id": str(run_id), "input": input_str})

    return TraceHandler()


async def run_langgraph_session(base_url: str, api_key: str, model: str, prompts: tuple[str, str],
                                request_ids: tuple[str, str], tool_ctx: ToolContext,
                                http_client: httpx.AsyncClient | None = None,
                                timeout_s: float = TIMEOUT_S) -> SessionResult:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode, tools_condition

    res = SessionResult("langgraph", framework_version("langgraph"))
    hooks = {"response": [res.capture.async_hook]}
    own_client = http_client is None
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=timeout_s, event_hooks=hooks)
    else:
        http_client.event_hooks["response"] = http_client.event_hooks.get("response", []) + hooks["response"]

    @tool
    def write_record(record_id: str, value: str) -> str:
        """Write a value into a customer record.

        Args:
            record_id: The customer record id, e.g. cust-0001.
            value: The text to store in the record.
        """
        return tool_ctx.write(record_id, value)

    llm = ChatOpenAI(model=model, base_url=base_url, api_key=api_key, max_retries=0, timeout=timeout_s,
                     http_async_client=http_client, streaming=False, use_responses_api=False)
    llm_tools = llm.bind_tools([write_record])

    async def agent_node(state: MessagesState):
        return {"messages": [await llm_tools.ainvoke(state["messages"])]}

    g = StateGraph(MessagesState)
    g.add_node("agent", agent_node)
    g.add_node("tools", ToolNode([write_record]))
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", tools_condition)
    g.add_edge("tools", "agent")
    app = g.compile(checkpointer=InMemorySaver())

    handler = _lc_trace_handler()
    cfg = {"configurable": {"thread_id": tool_ctx.session_id}, "callbacks": [handler], "recursion_limit": 12}
    try:
        for i, (prompt, rid) in enumerate(zip(prompts, request_ids)):
            tool_ctx.current_request_id = rid
            turn = TurnResult(rid)
            t0 = time.perf_counter()
            try:
                msgs = ([SystemMessage(AGENT_INSTRUCTIONS)] if i == 0 else []) + [HumanMessage(prompt)]
                out = await app.ainvoke({"messages": msgs}, config=cfg)
                last = out["messages"][-1]
                content = last.content
                if isinstance(content, list):
                    content = " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
                refusal = (getattr(last, "additional_kwargs", {}) or {}).get("refusal")
                turn.final_text = content if content else (refusal or "")
            except Exception as e:
                turn.error = f"{type(e).__name__}: {e}"[:2000]
            turn.duration_s = round(time.perf_counter() - t0, 3)
            res.turns.append(turn)
            if turn.error:
                break
    finally:
        if own_client:
            await http_client.aclose()
    res.trace_records = handler.records
    return res


RUNNERS = {"openai_agents": run_openai_agents_session, "langgraph": run_langgraph_session}
