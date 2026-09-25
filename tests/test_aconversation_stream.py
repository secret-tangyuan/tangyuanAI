"""v1.3.0 on_event 回调钩子测试 (#19)。

覆盖:
- sync conversation + 非流式 + on_event 是 list
- async aconversation + 流式 + on_event 是 sync / async callback
- tool_call round 中 on_event 收到 tool_call + done

复用 ``tests/_llm_mock.py`` mock 基础设施,走真实 wire 协议。
"""
from __future__ import annotations

import asyncio
import uuid as _uuid

import pytest
from _llm_mock import (
    MockState,
    _OpenAIMockHandler,
    _start_mock_server,
    openai_text_response,
    openai_tool_call_response,
)
from tangyuanAI import (
    Agent,
    activate_template,
    agent_list,
    template_agent,
    tool_registry,
)


@pytest.fixture
def openai_state():
    """mock OpenAI server + 共享 state。"""
    state = MockState()
    _OpenAIMockHandler.state = state
    base_url, server = _start_mock_server(_OpenAIMockHandler)
    yield state, base_url
    server.shutdown()
    server.server_close()
    _OpenAIMockHandler.state = None


@pytest.fixture(autouse=True)
def _clean_globals():
    saved_tools = dict(tool_registry._tools)
    saved_perms = dict(tool_registry._agent_permissions)
    agent_list.clear()
    yield
    agent_list.clear()
    tool_registry._tools.clear()
    tool_registry._agent_permissions.clear()
    tool_registry._tools.update(saved_tools)
    tool_registry._agent_permissions.update(saved_perms)


def _make_plain_agent(uuid_str: str, name: str, base_url: str):
    @template_agent(name, uuid=uuid_str, description="plain agent")
    class _P(Agent):
        protocol = "openai"
        prompt = "you are a test agent"
        model_name = "test-model"
        api_key = "test-key"
        api_provider = base_url + "/v1/chat/completions"
        stream = False  # 显式关闭流式,优先测非流式路径

    activate_template(name)
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001
    return inst


def _make_stream_agent(uuid_str: str, name: str, base_url: str):
    @template_agent(name, uuid=uuid_str, description="stream agent")
    class _P(Agent):
        protocol = "openai"
        prompt = "you are a test agent"
        model_name = "test-model"
        api_key = "test-key"
        api_provider = base_url + "/v1/chat/completions"
        stream = True  # 打开流式

    activate_template(name)
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001
    return inst


# ============================================================
# 1. sync conversation + 非流式 + on_event 是 list → text + done
# ============================================================


def test_conversation_sync_on_event_receives_text_and_done(openai_state):
    """v1.3.0 (#19): sync conversation 非流式 + on_event 收到 text + done。"""
    state, base_url = openai_state
    agent = _make_plain_agent(_uuid.uuid4().hex, "t", base_url)

    received: list = []
    state.queue(lambda _b: openai_text_response("hi back"))
    out = agent.conversation("hello", on_event=received.append)
    assert out == "hi back"

    types = [e.type for e in received]
    assert "text" in types
    assert "done" in types
    text_events = [e for e in received if e.type == "text"]
    assert any(e.text == "hi back" for e in text_events)


# ============================================================
# 2. async aconversation + 流式 + on_event 是 sync callback
# ============================================================


def test_aconversation_stream_on_event_sync_callback_fires(openai_state):
    """v1.3.0 (#19): async aconversation 流式 + on_event 是 sync list.append,收到 text + done。"""
    state, base_url = openai_state
    agent = _make_stream_agent(_uuid.uuid4().hex, "t", base_url)

    received: list = []

    async def _go():
        state.queue(lambda _b: openai_text_response("streamed reply"))
        out = await agent.aconversation("hi", on_event=received.append)
        return out

    out = asyncio.run(_go())
    assert out == "streamed reply"

    types = [e.type for e in received]
    assert "text" in types
    assert "done" in types


# ============================================================
# 3. async aconversation + 流式 + on_event 是 async callback,验证 awaitable 被 await
# ============================================================


def test_aconversation_stream_on_event_async_callback_awaited(openai_state):
    """v1.3.0 (#19): async callback 必须被 await(顺序执行 + 状态可读)。"""
    state, base_url = openai_state
    agent = _make_stream_agent(_uuid.uuid4().hex, "t", base_url)

    events_order: list = []

    async def async_on_event(evt):
        events_order.append(evt.type)

    async def _go():
        state.queue(lambda _b: openai_text_response("ok"))
        return await agent.aconversation("hi", on_event=async_on_event)

    out = asyncio.run(_go())
    assert out == "ok"
    assert events_order, "async callback 至少收到一个 evt"
    assert "done" in events_order, f"应收到 done,实际: {events_order}"


# ============================================================
# 4. tool_call round 中 on_event 收到 tool_call + done
# ============================================================


def test_aconversation_on_event_fires_for_tool_call(openai_state):
    """v1.3.0 (#19): tool_call 流程中 on_event 收到 tool_call 事件。"""
    state, base_url = openai_state
    agent = _make_stream_agent(_uuid.uuid4().hex, "t", base_url)

    received: list = []

    async def _go():
        state.queue(lambda _b: openai_tool_call_response("call_1", "echo", {"text": "x"}))
        # 第二次 FC 续轮 mock:纯文本回复
        state.queue(lambda _b: openai_text_response("done after tool"))
        return await agent.aconversation("hi", on_event=received.append)

    out = asyncio.run(_go())
    # tool_call 那轮文本为空(LLM 只派 tool 没给 text),最终 out 是 done after tool
    assert out == "done after tool"

    types = [e.type for e in received]
    assert "tool_call" in types, f"应收到 tool_call,实际: {types}"
    # tool_call evt 至少有 id/name
    tc_evts = [e for e in received if e.type == "tool_call" and e.tool_call]
    assert tc_evts
    assert tc_evts[0].tool_call.name == "echo"


# ============================================================
# 5. on_event 异常被吞掉,不打破对话(不影响 out)
# ============================================================


def test_aconversation_on_event_exception_swallowed(openai_state):
    """v1.3.0 (#19): on_event callback 抛异常时,对话仍正常完成。"""
    state, base_url = openai_state
    agent = _make_plain_agent(_uuid.uuid4().hex, "t", base_url)

    def bad_callback(evt):
        if evt.type == "text":
            raise RuntimeError("intentional error from on_event")

    state.queue(lambda _b: openai_text_response("survived"))
    out = agent.conversation("hi", on_event=bad_callback)
    assert out == "survived", "on_event 异常被吞掉,对话正常返回"
