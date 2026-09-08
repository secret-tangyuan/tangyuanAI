# -*- coding: utf-8 -*-
"""
BaseAgent (OpenAI 协议) 平行测试 —— 验证与 AnthropicAgent 行为对称。

覆盖：

- non-stream 文本返回（OpenAI 协议本来就 OK；这里做基线 + 防回归）
- stream 文本返回
- tool_calls + text 混响
- 公开 API 与 AnthropicAgent 对齐（get_all_available_tools / pack / 4 个模板管理 builtin_tool）

mock 基础设施见 ``_llm_mock.py``。
"""
from __future__ import annotations

import uuid as _uuid

import pytest
from _llm_mock import (
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
from tangyuanAI.Agent_list import (
    agent_template_pool,
)

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def openai_state():
    """起一个 mock OpenAI server，注入共享 state。返回 (state, base_url)。"""
    from _llm_mock import MockState
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


def _make_openai_agent(uuid_str: str, name: str, base_url: str, use_stream: bool):
    """建一个 OpenAI 协议 Agent，api_provider 指向 mock。"""

    @template_agent(name, uuid=uuid_str, description="test")
    class _OA(Agent):
        protocol = "openai"  # 显式选 OpenAI
        prompt = "you are a test agent"
        model_name = "test-model"
        api_key = "test-key"
        api_provider = base_url + "/v1/chat/completions"
        stream = use_stream

    activate_template(name)
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001
    return inst


def _register_echo(agent_name: str = "oa") -> None:
    @tool_registry.register_tool(
        allowed_agents=[agent_name],
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


# ===========================================================================
# OpenAI non-stream 文本基线（v0.3.0 本身就 OK；这里防回归）
# ===========================================================================

def test_openai_non_stream_pure_text(openai_state):
    state, base_url = openai_state
    agent = _make_openai_agent(_uuid.uuid4().hex, "oa", base_url, use_stream=False)
    _register_echo("oa")

    state.queue(lambda _body: openai_text_response("hi from openai"))
    out = agent.conversation("hello")
    assert out == "hi from openai"
    assert state.real_call_count == 1


def test_openai_stream_pure_text(openai_state):
    state, base_url = openai_state
    agent = _make_openai_agent(_uuid.uuid4().hex, "oa", base_url, use_stream=True)
    _register_echo("oa")

    state.queue(lambda _body: openai_text_response("stream openai"))
    out = agent.conversation("hello")
    assert out == "stream openai"


def test_openai_tool_call_then_text(openai_state):
    state, base_url = openai_state
    agent = _make_openai_agent(_uuid.uuid4().hex, "oa", base_url, use_stream=False)
    _register_echo("oa")

    state.queue(lambda _body: openai_tool_call_response(
        "call_1", "echo", {"text": "yo"},
    ))
    state.queue(lambda _body: openai_text_response("finished"))
    out = agent.conversation("call tool")
    assert out == "finished"
    assert state.real_call_count == 2


# ===========================================================================
# 公开 API 对齐
# ===========================================================================

def test_base_agent_has_template_builtin_tools():
    for name in ("list_templates", "activate_template", "deactivate_template", "register_template"):
        assert hasattr(BaseAgent, name), f"BaseAgent missing {name}"
        assert callable(getattr(BaseAgent, name))


def test_base_agent_get_all_available_tools(openai_state):
    _, base_url = openai_state
    agent = _make_openai_agent(_uuid.uuid4().hex, "oa", base_url, use_stream=False)
    _register_echo("oa")
    names = agent.get_all_available_tools()
    assert "echo" in names
    for builtin in ("ask_for_help", "list_agents", "attempt_completion", "reload",
                    "list_templates", "activate_template", "deactivate_template", "register_template"):
        assert builtin in names


def test_base_agent_pack_constructs_envelope():
    from tangyuanAI import BaseAgent
    captured = []
    inst = object.__new__(BaseAgent)
    inst.uuid = "u-oa"
    inst.name = "oa"
    inst.current_task_id = "tid-1"
    inst.out = lambda content: captured.append(content)  # type: ignore[assignment]

    inst.pack("hi", finish_task=False)
    assert captured[-1]["message"] == "hi"
    assert captured[-1]["ai_uuid"] == "u-oa"
    assert captured[-1]["task_id"] == "tid-1"
    assert captured[-1]["task"] is False

    captured.clear()
    inst.pack(finish_task=True)
    assert captured[-1]["task"] is True
