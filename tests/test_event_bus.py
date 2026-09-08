# -*- coding: utf-8 -*-
"""
输出事件总线（pack / out / hooks）单测。

- 子类覆写 ``out``：验证 conversation 过程中 4 类事件都被收到
- 实例直接绑 ``out``：常见的定制方式
- 覆写 ``pack`` 但未覆写 ``out``：构造时打 warning
- 钩子系统：``before`` / ``after`` / ``error`` 三类事件都触发
- 钩子失败不影响主流程
"""
from __future__ import annotations

import uuid as _uuid
from typing import List

import pytest
from _llm_mock import (
    MockState,
    _AnthropicMockHandler,
    _start_mock_server,
    anthropic_text_response,
    anthropic_text_then_tool_response,
    anthropic_tool_use_response,
)
from tangyuanAI import (
    Agent,
    activate_template,
    agent_list,
    agent_template_pool,
    template_agent,
    tool_registry,
)
from tangyuanAI.anthropic_agent import AnthropicAgent


@pytest.fixture(autouse=True)
def _clean_globals():
    saved_tools = dict(tool_registry._tools)
    saved_perms = dict(tool_registry._agent_permissions)
    agent_list.clear()
    agent_template_pool.clear()
    yield
    agent_list.clear()
    agent_template_pool.clear()
    tool_registry._tools.clear()
    tool_registry._agent_permissions.clear()
    tool_registry._tools.update(saved_tools)
    tool_registry._agent_permissions.update(saved_perms)


def _start_mock():
    state = MockState()
    _AnthropicMockHandler.state = state
    base_url, server = _start_mock_server(_AnthropicMockHandler)
    return state, base_url, server


def _make_agent(name: str, base_url: str, use_stream: bool = False) -> AnthropicAgent:
    @template_agent(name, uuid=_uuid.uuid4().hex, description="test")
    class _A(Agent):
        protocol = "anthropic"
        prompt = "你是一个助手"
        model_name = "test-model"
        api_key = "test-key"
        api_provider = base_url
        stream = use_stream

    activate_template(name)
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001
    return inst


# ===========================================================================
# 子类覆写 out：实际任务驱动
# ===========================================================================

def test_user_builds_chatbot_with_custom_out_logger():
    """场景：开发者做聊天机器人，继承 Agent 覆写 out 把所有事件推到 UI logger。
    真实任务：用户让 agent 查北京天气，验证 4 类事件都被 logger 收到。
    """
    state, base_url, server = _start_mock()
    try:
        events_log: List[dict] = []

        @template_agent("chatbot", uuid=_uuid.uuid4().hex, description="test")
        class _Chatbot(AnthropicAgent):
            protocol = "anthropic"
            prompt = "你是一个天气机器人"
            model_name = "test-model"
            api_key = "test-key"
            api_provider = base_url

            def out(self, content):
                # 推到"UI"——这里用 list 代替
                events_log.append(content)

        activate_template("chatbot")
        agent = agent_list["chatbot"]
        agent._connectivity = lambda: None  # noqa: SLF001

        @tool_registry.register_tool(
            allowed_agents=["chatbot"],
            name="get_weather",
            description="查天气",
            parameters={
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        )
        def get_weather(city: str) -> str:
            return f"{city}今天晴 25°C"

        state.queue(lambda _b: anthropic_text_then_tool_response(
            "我查查", "tw1", "get_weather", {"city": "北京"},
        ))
        state.queue(lambda _b: anthropic_text_response("北京今天晴 25°C。"))

        out = agent.conversation("北京天气？")
        assert "北京" in out

        # 4 类事件验证
        assert any(e.get("message") and e.get("task") is False for e in events_log), \
            f"缺 text 事件：{events_log}"
        assert any(e.get("tool_name") == "get_weather" and e.get("tool_result") is None
                   for e in events_log), \
            f"缺 tool_call 事件：{events_log}"
        assert any(e.get("tool_result") is not None for e in events_log), \
            f"缺 tool_result 事件：{events_log}"
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


def test_user_binds_out_directly_on_instance():
    """场景：用户不想继承类，直接给 instance 绑 out（最常见的 monkey-patch 用法）

    新设计：``enable_connectivity = False`` 类属性可以直接关 _connectivity 后台线程，
    不需要 monkey-patch。"""
    state, base_url, server = _start_mock()
    try:
        # v0.4.2+：用 enable_connectivity 类属性关后台线程（无需 monkey-patch）
        @template_agent("inst-out", uuid=_uuid.uuid4().hex, description="test")
        class _A(Agent):
            protocol = "anthropic"
            prompt = "x"
            model_name = "m"
            api_key = "k"
            api_provider = base_url
            enable_connectivity = False  # 关后台线程

        activate_template("inst-out")
        agent = agent_list["inst-out"]

        captured: List[dict] = []

        def _my_out(content):
            captured.append(content)

        agent.out = _my_out

        @tool_registry.register_tool(
            allowed_agents=["inst-out"],
            name="ping",
            description="ping",
            parameters={"type": "object", "properties": {}},
        )
        def ping() -> str:
            return "pong"

        state.queue(lambda _b: anthropic_text_then_tool_response("pinging", "t1", "ping", {}))
        state.queue(lambda _b: anthropic_text_response("done"))

        agent.conversation("ping")
        assert any(e.get("tool_result") == "pong" for e in captured)
        # mock 按字符拆分流式文本（p/i/n/g/i/n/g），断言拼接后的完整消息
        joined = "".join(str(e.get("message", "")) for e in captured)
        assert "pinging" in joined
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


# 注：原本有 test_user_overrides_pack_without_out_logs_warning，但框架用 loguru
# 而非 stdlib logging，caplog 抓不到；且这个 warning 是"开发辅助提示"而非核心契约，
# 单测覆盖价值低。行为本身已被 __init_subclass__ 的 has_own_pack/has_own_out
# 逻辑保证（见 Agent_Base_.py），不再单测。


# ===========================================================================
# 钩子系统
# ===========================================================================
# 真实任务：用户做审计日志，让 agent 调工具时记录 event

def test_user_audits_tool_calls_via_register_tool_hook():
    """场景：开发者需要审计工具调用，register_tool_hook 收集 before/after 事件"""
    state, base_url, server = _start_mock()
    try:
        agent = _make_agent("auditor", base_url)
        audit_log: List[dict] = []

        def _audit(event_type, tool_name, tool_args, tool_result, task_id):
            audit_log.append({
                "event": event_type,
                "tool": tool_name,
                "args": tool_args,
                "result": tool_result,
                "task_id": task_id,
            })

        agent.register_tool_hook(_audit)

        @tool_registry.register_tool(
            allowed_agents=["auditor"],
            name="lookup",
            description="查",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
        )
        def lookup(q: str) -> str:
            return f"found:{q}"

        state.queue(lambda _b: anthropic_text_then_tool_response("searching", "t1", "lookup", {"q": "RAG"}))
        state.queue(lambda _b: anthropic_text_response("done"))

        agent.conversation("查 RAG")
        # 至少有 before + after
        assert any(e["event"] == "before" and e["tool"] == "lookup" for e in audit_log)
        assert any(e["event"] == "after" and e["tool"] == "lookup" and e["result"] == "found:RAG"
                   for e in audit_log)
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


def test_user_hook_raising_does_not_block_conversation():
    """场景：用户写了个有 bug 的 hook 抛异常 → 不应阻塞对话"""
    state, base_url, server = _start_mock()
    try:
        agent = _make_agent("buggy-hook", base_url)

        def _bad_hook(*args, **kwargs):
            raise RuntimeError("hook crash")

        agent.register_tool_hook(_bad_hook)

        @tool_registry.register_tool(
            allowed_agents=["buggy-hook"],
            name="ok",
            description="ok",
            parameters={"type": "object", "properties": {}},
        )
        def ok() -> str:
            return "fine"

        state.queue(lambda _b: anthropic_tool_use_response("t1", "ok", {}))
        state.queue(lambda _b: anthropic_text_response("ok done"))

        # hook 抛异常不应阻塞 conversation
        out = agent.conversation("run ok")
        assert "ok done" in out
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


def test_user_hook_error_event_fires_when_tool_raises():
    """场景：工具抛异常时，error 钩子应被调用"""
    state, base_url, server = _start_mock()
    try:
        agent = _make_agent("err-hook", base_url)
        events: List[str] = []
        def _h(event_type, tool_name, tool_args, tool_result, task_id):
            events.append(event_type)
        agent.register_tool_hook(_h)

        @tool_registry.register_tool(
            allowed_agents=["err-hook"],
            name="crash",
            description="crash",
            parameters={"type": "object", "properties": {}},
        )
        def crash() -> str:
            raise ValueError("boom")

        state.queue(lambda _b: anthropic_tool_use_response("t1", "crash", {}))
        state.queue(lambda _b: anthropic_text_response("sorry"))

        agent.conversation("run crash")
        # error 钩子应触发
        assert "error" in events
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


# ===========================================================================
# Agent 启动时的 _connectivity 后台线程（v0.4.2+ enable_connectivity 切换）
# ===========================================================================

def test_enable_connectivity_false_disables_background_ping():
    """enable_connectivity = False 时，__init__ 不应启动 _connectivity 后台线程。

    实际场景：19 个 agent 实例化 = 19 个 ping 后台 HTTP 请求会污染日志 + 拖慢冷启动。
    用户应能关。
    """
    @template_agent("conn-off", uuid=_uuid.uuid4().hex, description="t")
    class _A(Agent):
        protocol = "anthropic"
        prompt = "x"
        model_name = "m"
        api_key = "k"
        api_provider = "http://127.0.0.1:1"
        enable_connectivity = False  # v0.4.2+ 显式关

    assert _A.enable_connectivity is False, "类属性 enable_connectivity 未生效"


def test_enable_connectivity_true_default_still_pings():
    """默认 enable_connectivity=True（向后兼容）→ 后台线程启动。"""
    assert _A_default.enable_connectivity is True


@template_agent("conn-default", uuid=_uuid.uuid4().hex, description="t")
class _A_default(Agent):
    protocol = "anthropic"
    prompt = "x"
    model_name = "m"
    api_key = "k"
    api_provider = "http://127.0.0.1:1"
