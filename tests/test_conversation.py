# -*- coding: utf-8 -*-
"""``conversation`` / ``aconversation`` 新参数行为单测（v1.3.0+）。

覆盖：
- ``addhistory=False`` —— 不写 user 消息到 history，但仍返回 LLM 回复
- ``tooluse=False`` —— 即便 ``fc_model=True`` 也不派发 tools schema、不走 FC 续轮
- ``conversation_with_tool`` deprecated alias —— 仍可调用 + 触发 DeprecationWarning
- async 版同样行为

mock 基础设施见 ``_llm_mock.py``。
"""
from __future__ import annotations

import asyncio
import uuid as _uuid
import warnings

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
    BaseAgent,
    activate_template,
    agent_list,
    template_agent,
    tool_registry,
)
from tangyuanAI.Agent_list import agent_template_pool


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

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
    agent_template_pool.clear()
    yield
    agent_list.clear()
    agent_template_pool.clear()
    tool_registry._tools.clear()
    tool_registry._agent_permissions.clear()
    tool_registry._tools.update(saved_tools)
    tool_registry._agent_permissions.update(saved_perms)


def _make_fc_agent(uuid_str: str, name: str, base_url: str, use_stream: bool = False):
    """建一个 fc_model=True 的 OpenAI Agent，方便验证 tooluse=False 跳过 FC。"""

    @template_agent(name, uuid=uuid_str, description="fc test agent")
    class _FC(Agent):
        protocol = "openai"
        prompt = "you are a test agent"
        model_name = "test-model"
        api_key = "test-key"
        api_provider = base_url + "/v1/chat/completions"
        stream = use_stream
        fc_model = True  # 显式打开 FC，后面测试会切 tooluse=False 关掉

    activate_template(name)
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001
    return inst


def _make_plain_agent(uuid_str: str, name: str, base_url: str, use_stream: bool = False):
    """建一个 fc_model=False 的 OpenAI Agent。"""

    @template_agent(name, uuid=uuid_str, description="plain agent")
    class _P(Agent):
        protocol = "openai"
        prompt = "you are a test agent"
        model_name = "test-model"
        api_key = "test-key"
        api_provider = base_url + "/v1/chat/completions"
        stream = use_stream

    activate_template(name)
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001
    return inst


def _register_echo(name: str = "t") -> None:
    @tool_registry.register_tool(
        allowed_agents=[name],
        name="echo",
        description="echo back",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    def echo(text: str) -> str:
        return f"echo:{text}"


# ---------------------------------------------------------------------------
# conversation 默认行为：与旧 conversation_with_tool 等价
# ---------------------------------------------------------------------------

def test_conversation_default_appends_user_message(openai_state):
    """addhistory 默认 True → user 消息进 history。"""
    state, base_url = openai_state
    agent = _make_plain_agent(_uuid.uuid4().hex, "t", base_url)

    state.queue(lambda _body: openai_text_response("hi back"))
    out = agent.conversation("hello")
    assert out == "hi back"
    # history 里应至少有一条 user 消息
    roles = [m.get("role") for m in agent.history if isinstance(m, dict)]
    assert "user" in roles


def test_conversation_returns_reply(openai_state):
    """conversation 仍返回 LLM 文本。"""
    state, base_url = openai_state
    agent = _make_plain_agent(_uuid.uuid4().hex, "t", base_url)

    state.queue(lambda _body: openai_text_response("one-shot reply"))
    out = agent.conversation("hi", addhistory=False)
    assert out == "one-shot reply"


# ---------------------------------------------------------------------------
# addhistory=False：不写 history
# ---------------------------------------------------------------------------

def test_conversation_addhistory_false_does_not_mutate_history(openai_state):
    """addhistory=False 时 user 消息不进 history。"""
    state, base_url = openai_state
    agent = _make_plain_agent(_uuid.uuid4().hex, "t", base_url)

    before = [m for m in agent.history if isinstance(m, dict)]
    state.queue(lambda _body: openai_text_response("ephemeral reply"))
    out = agent.conversation("ignored", addhistory=False)
    assert out == "ephemeral reply"
    after = [m for m in agent.history if isinstance(m, dict)]
    # history 完全没变（system 行如果有也算"没新增 user"）
    assert before == after
    assert not any(m.get("role") == "user" for m in after)


def test_conversation_addhistory_false_returns_reply(openai_state):
    """addhistory=False 仍能拿到回复文本（一次性 AI 调用）。"""
    state, base_url = openai_state
    agent = _make_plain_agent(_uuid.uuid4().hex, "t", base_url)

    state.queue(lambda _body: openai_text_response("classified: positive"))
    out = agent.conversation(
        "请分类以下文本为 positive/negative",
        addhistory=False, tooluse=False,
    )
    assert out == "classified: positive"


# ---------------------------------------------------------------------------
# tooluse=False：即便 fc_model=True 也不派发 tools schema
# ---------------------------------------------------------------------------

def test_conversation_tooluse_false_skips_tools_schema(openai_state):
    """tooluse=False 时 LLM request 的 tools 字段应为空。"""
    state, base_url = openai_state
    agent = _make_fc_agent(_uuid.uuid4().hex, "t", base_url)
    _register_echo("t")

    captured: list[dict] = []
    state.queue(lambda body: (captured.append(body), openai_text_response("pure chat"))[1])
    out = agent.conversation("hi", tooluse=False)
    assert out == "pure chat"
    assert state.real_call_count == 1
    # request 里 tools 必须是空（tooluse=False 时 _collect_tools_schema 返回 []）
    assert captured, "expected to capture request body"
    req_body = captured[0]
    # OpenAI 协议里 tools 是顶层字段
    assert req_body.get("tools") in (None, [],), f"tools should be empty, got {req_body.get('tools')!r}"


def test_conversation_tooluse_false_skips_fc_recursion(openai_state):
    """tooluse=False 即便 LLM 响应里硬塞 tool_calls 也不递归。"""
    state, base_url = openai_state
    agent = _make_fc_agent(_uuid.uuid4().hex, "t", base_url)
    _register_echo("t")

    # LLM 尝试派 tool call（openai_tool_call_response 返回含 tool_calls 的响应）
    state.queue(lambda _body: openai_tool_call_response("call_1", "echo", {"text": "x"}))

    out = agent.conversation("hi", tooluse=False)
    # tooluse=False → 不递归 → 返回 LLM 末轮文本（这里 LLM 没给文本所以空串）
    # 关键断言：只调了 1 次 LLM（如果 FC 递归会发生 echo 调用 + 续轮调用）
    assert state.real_call_count == 1, "tooluse=False 应避免 FC 续轮"
    # echo 工具不应该被执行（real_call_count=1 已经隐含）
    assert out == ""


# ---------------------------------------------------------------------------
# deprecated alias
# ---------------------------------------------------------------------------

def test_conversation_with_tool_deprecated_warns(openai_state):
    """旧名仍能用但会触发 DeprecationWarning。"""
    state, base_url = openai_state
    agent = _make_plain_agent(_uuid.uuid4().hex, "t", base_url)

    state.queue(lambda _body: openai_text_response("via alias"))
    with pytest.warns(DeprecationWarning, match="conversation_with_tool is deprecated"):
        out = agent.conversation_with_tool("hi")
    assert out == "via alias"


def test_aconversation_with_tool_deprecated_warns(openai_state):
    """async 旧名同样打 warning。"""
    state, base_url = openai_state
    agent = _make_plain_agent(_uuid.uuid4().hex, "t", base_url)

    async def _go():
        state.queue(lambda _body: openai_text_response("via async alias"))
        with pytest.warns(DeprecationWarning, match="aconversation_with_tool is deprecated"):
            out = await agent.aconversation_with_tool("hi")
        return out

    assert asyncio.run(_go()) == "via async alias"


# ---------------------------------------------------------------------------
# async 版 addhistory=False
# ---------------------------------------------------------------------------

def test_aconversation_addhistory_false_does_not_mutate_history(openai_state):
    """async 版 addhistory=False 也不写 history。"""
    state, base_url = openai_state
    agent = _make_plain_agent(_uuid.uuid4().hex, "t", base_url)

    async def _go():
        before = [m for m in agent.history if isinstance(m, dict)]
        state.queue(lambda _body: openai_text_response("async ephemeral"))
        out = await agent.aconversation("hi", addhistory=False)
        after = [m for m in agent.history if isinstance(m, dict)]
        return out, before, after

    out, before, after = asyncio.run(_go())
    assert out == "async ephemeral"
    assert before == after
