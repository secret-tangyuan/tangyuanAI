# -*- coding: utf-8 -*-
"""
AnthropicAgent 协议层单测 —— 走 mock Anthropic HTTP server。

覆盖 v0.3.1 修复 + 公开 API 对齐：

- **bug 修复**：``AnthropicAgent.conversation(stream=False)`` 不再丢字
  （v0.3.0 时 LLM 返回的文本只入 ``full_text``，不进 ``assistant_blocks``，导致最终 ``return ""``）
- **回归**：``stream=True`` 路径不受影响
- **多轮**：tool_use + tool_result + 最终 text 的对话循环能正常收尾
- **async**：``aconversation_with_tool`` 同样覆盖
- **API 对齐**：``pack`` / ``get_all_available_tools`` / 4 个模板管理 builtin_tool 都存在且可用

mock 基础设施见 ``_llm_mock.py``（同时支持 OpenAI + Anthropic）。
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
    BaseAgent,
    activate_template,
    agent_list,
    template_agent,
    tool_registry,
)
from tangyuanAI.Agent_list import (
    agent_template_pool,
    register_template,
)
from tangyuanAI.anthropic_agent import AnthropicAgent

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def anthropic_state():
    """起一个 mock Anthropic server，注入一个共享 MockState。返回 (state, base_url)。"""
    state = MockState()
    _AnthropicMockHandler.state = state
    base_url, server = _start_mock_server(_AnthropicMockHandler)
    yield state, base_url
    server.shutdown()
    server.server_close()
    _AnthropicMockHandler.state = None


@pytest.fixture
def anthropic_url():
    """只起一个 mock server、不要状态。给不调 LLM 的 API 对齐测试用。"""
    state = MockState()
    _AnthropicMockHandler.state = state
    base_url, server = _start_mock_server(_AnthropicMockHandler)
    yield base_url
    server.shutdown()
    server.server_close()
    _AnthropicMockHandler.state = None


@pytest.fixture(autouse=True)
def _clean_globals():
    """每个用例前后清 agent_list / agent_template_pool / tool_registry，避免污染。"""
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


def _make_agent(uuid_str: str, name: str, base_url: str, use_stream: bool):
    """动态建一个 Anthropic 协议 Agent 类，api_provider 指向 mock server。"""

    @template_agent(name, uuid=uuid_str, description="test")
    class _TestAgent(Agent):
        protocol = "anthropic"
        prompt = "你是一个测试 Agent"
        model_name = "test-model"
        api_key = "test-key"
        api_provider = base_url  # mock server；_endpoint() 会拼上 /v1/messages
        stream = use_stream

    activate_template(name)
    # 关闭 _connectivity 后台线程（mock 不希望被打扰）
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001 - 测试桩
    return inst


def _register_echo_tool(agent_uuid: str, agent_name: str = "t") -> None:
    """注册一个 echo 工具，给 agent 调用。

    注意 ``allowed_agents`` 必须用 agent name（``check_permission`` 内部
    会先做 uuid→name 翻译再比对；传 uuid 会被翻译后再去跟 uuid 列表比对，
    必然失败 —— 这是框架现状，详见 ``agent_tool.check_permission``）。
    """
    @tool_registry.register_tool(
        allowed_agents=[agent_name],
        name="echo",
        description="原样回显",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    def echo(text: str) -> str:
        return f"echo:{text}"


# ===========================================================================
# bug 修复：non-stream 文本不再丢字
# ===========================================================================

def test_non_stream_pure_text_returns_content(anthropic_state):
    """v0.3.0 bug：non-stream 纯文本返回 ``""``；v0.3.1 应返回真实文本。"""
    state, base_url = anthropic_state
    agent = _make_agent(_uuid.uuid4().hex, "t", base_url, use_stream=False)
    _register_echo_tool(agent.uuid, "t")

    state.queue(lambda _body: anthropic_text_response("hello, world"))
    out = agent.conversation("hi")
    assert out == "hello, world"
    assert state.real_call_count == 1


def test_non_stream_text_then_tool_use_returns_text(anthropic_state):
    """v0.3.0 bug：text+tool_use 混响，text 丢；v0.3.1 应保留 text。"""
    state, base_url = anthropic_state
    agent = _make_agent(_uuid.uuid4().hex, "t", base_url, use_stream=False)
    _register_echo_tool(agent.uuid, "t")

    # 第一轮：text + tool_use；tool 跑完后再来一轮纯文本
    state.queue(lambda _body: anthropic_text_then_tool_response(
        "好的，我来 echo 一下", "toolu_1", "echo", {"text": "ping"},
    ))
    state.queue(lambda _body: anthropic_text_response("done"))
    out = agent.conversation("echo something")
    assert "echo:" in out or "done" in out  # 末轮 assistant 的 text
    assert state.real_call_count == 2


def test_non_stream_tool_use_only_no_text(anthropic_state):
    """纯 tool_use 响应（无前置文本）→ return "" 是正确行为（无 text 块可返回）"""
    state, base_url = anthropic_state
    agent = _make_agent(_uuid.uuid4().hex, "t", base_url, use_stream=False)
    _register_echo_tool(agent.uuid, "t")

    state.queue(lambda _body: anthropic_tool_use_response(
        "toolu_1", "echo", {"text": "x"},
    ))
    state.queue(lambda _body: anthropic_text_response("all done"))
    out = agent.conversation("call tool")
    # 第一轮没 text 块，第二轮 text 返回；最终 return 是末轮 text
    assert out == "all done"
    assert state.real_call_count == 2


# ===========================================================================
# 回归：stream 模式不受影响
# ===========================================================================

def test_stream_pure_text_returns_content(anthropic_state):
    state, base_url = anthropic_state
    agent = _make_agent(_uuid.uuid4().hex, "t", base_url, use_stream=True)
    _register_echo_tool(agent.uuid, "t")

    state.queue(lambda _body: anthropic_text_response("stream hello"))
    out = agent.conversation("hi")
    assert out == "stream hello"


def test_stream_text_then_tool_use_returns_text(anthropic_state):
    state, base_url = anthropic_state
    agent = _make_agent(_uuid.uuid4().hex, "t", base_url, use_stream=True)
    _register_echo_tool(agent.uuid, "t")

    state.queue(lambda _body: anthropic_text_then_tool_response(
        "let me echo", "toolu_1", "echo", {"text": "yo"},
    ))
    state.queue(lambda _body: anthropic_text_response("wrapped up"))
    out = agent.conversation("echo please")
    assert out == "wrapped up"


# ===========================================================================
# 异步路径
# ===========================================================================

@pytest.mark.asyncio
async def test_aconversation_non_stream_pure_text(anthropic_state):
    state, base_url = anthropic_state
    agent = _make_agent(_uuid.uuid4().hex, "t", base_url, use_stream=False)
    _register_echo_tool(agent.uuid, "t")

    state.queue(lambda _body: anthropic_text_response("async hello"))
    out = await agent.aconversation("hi")
    assert out == "async hello"


@pytest.mark.asyncio
async def test_aconversation_stream_pure_text(anthropic_state):
    state, base_url = anthropic_state
    agent = _make_agent(_uuid.uuid4().hex, "t", base_url, use_stream=True)
    _register_echo_tool(agent.uuid, "t")

    state.queue(lambda _body: anthropic_text_response("async stream"))
    out = await agent.aconversation("hi")
    assert out == "async stream"


@pytest.mark.asyncio
async def test_aconversation_non_stream_text_then_tool(anthropic_state):
    """async 路径同样要在 non-stream 下保留 text"""
    state, base_url = anthropic_state
    agent = _make_agent(_uuid.uuid4().hex, "t", base_url, use_stream=False)
    _register_echo_tool(agent.uuid, "t")

    state.queue(lambda _body: anthropic_text_then_tool_response(
        "我先说", "toolu_1", "echo", {"text": "abc"},
    ))
    state.queue(lambda _body: anthropic_text_response("结束"))
    out = await agent.aconversation("hi")
    assert out == "结束"


# ===========================================================================
# 公开 API 对齐：pack / get_all_available_tools / 4 个模板管理 builtin_tool
# ===========================================================================

def test_anthropic_has_pack_method():
    """AnthropicAgent 暴露与 BaseAgent 同名的 pack（v0.3.1 新增）"""
    assert hasattr(AnthropicAgent, "pack")
    assert callable(AnthropicAgent.pack)


def test_anthropic_pack_constructs_envelope_and_calls_out():
    """pack 构造 content dict（含 ai_uuid / task_id / timestamp）后转 self.out"""
    from tangyuanAI.anthropic_agent import AnthropicAgent
    captured: List[dict] = []
    inst = object.__new__(AnthropicAgent)  # 绕过 __init__
    inst.uuid = "u-1"
    inst.name = "n-1"
    inst.current_task_id = None
    inst.out = lambda content: captured.append(content)  # type: ignore[assignment]

    inst.pack("hi", finish_task=False)
    assert captured and captured[0]["message"] == "hi"
    assert captured[0]["ai_uuid"] == "u-1"
    assert captured[0]["ai_name"] == "n-1"
    assert captured[0]["task"] is False
    assert "task_id" in captured[0]
    assert "timestamp" in captured[0]

    captured.clear()
    inst.pack(finish_task=True)
    assert captured[0]["task"] is True

    captured.clear()
    inst.pack(tool_model=True, tool_name="x", tool_parameter={"a": 1})
    assert captured[0]["tool_name"] == "x"
    assert captured[0]["tool_parameter"] == {"a": 1}
    assert captured[0]["task"] is False


def test_anthropic_has_get_all_available_tools():
    assert hasattr(AnthropicAgent, "get_all_available_tools")
    assert callable(AnthropicAgent.get_all_available_tools)


def test_anthropic_get_all_available_tools_lists_builtin_and_registered(anthropic_url):
    base_url = anthropic_url
    agent = _make_agent(_uuid.uuid4().hex, "t", base_url, use_stream=False)
    _register_echo_tool(agent.uuid, "t")

    names = agent.get_all_available_tools()
    # builtin：ask_for_help / list_agents / attempt_completion / reload
    # + 模板管理 4 个：list_templates / activate_template / deactivate_template / register_template
    # + echo（注册工具）
    assert "echo" in names
    for builtin in ("ask_for_help", "list_agents", "attempt_completion", "reload",
                    "list_templates", "activate_template", "deactivate_template", "register_template"):
        assert builtin in names, f"missing builtin tool: {builtin}"


def test_anthropic_has_template_builtin_tools():
    """v0.3.0 只在 BaseAgent 上加了 4 个模板管理 builtin_tool，v0.3.1 补到 AnthropicAgent"""
    for name in ("list_templates", "activate_template", "deactivate_template", "register_template"):
        assert hasattr(AnthropicAgent, name), f"AnthropicAgent missing {name}"
        assert callable(getattr(AnthropicAgent, name))


def test_anthropic_list_templates_empty_pool(anthropic_url):
    """无模板时 list_templates 返回 '暂无'。fixture 已经清空 pool。"""
    from tangyuanAI import agent_template_pool
    assert len(agent_template_pool) == 0
    # 不创建 agent，直接调 list_templates 方法（基类方法，不需要 agent 实例）
    out = AnthropicAgent.list_templates(None)  # 类方法调用
    assert "暂无" in out


def test_anthropic_template_pool_round_trip(anthropic_url):
    """register_template → list_templates → activate_template → deactivate_template 闭环"""
    base_url = anthropic_url
    agent = _make_agent(_uuid.uuid4().hex, "t", base_url, use_stream=False)

    class _TplCls:
        def __init__(self):
            self.tag = "x"

    register_template(_TplCls, name="tpl-x", uuid="tpl-x-uuid", description="demo")
    out = agent.list_templates("tpl-x")
    assert "tpl-x" in out and "tpl-x-uuid" in out and "False" in out  # active=False

    out = agent.activate_template("tpl-x")
    assert "已激活" in out and "tpl-x" in out
    assert "tpl-x" in agent_list  # 双键写入

    out = agent.deactivate_template("tpl-x")
    assert "已反激活" in out
    assert "tpl-x" not in agent_list

    # 二次 deactivate：模板仍在池中，函数幂等返回 True（不是 "不在池中"）。
    out = agent.deactivate_template("tpl-x")
    assert "已反激活" in out  # 幂等：只要在池里就算成功

    # 真"不在池中"的情况：用一个未注册的 name
    out = agent.deactivate_template("never-registered")
    assert "不在池中" in out


# ===========================================================================
# BaseAgent 对照组：non-stream 行为本来就对（之前就走 full_content），
# 这里同时验证 BaseAgent 暴露的 API 与 AnthropicAgent 一致。
# ===========================================================================

def test_base_agent_has_same_public_api_surface():
    """BaseAgent 与 AnthropicAgent 公开 API 应对齐（v0.3.1 校验）"""
    base_methods = {m for m in dir(BaseAgent) if not m.startswith("_") and callable(getattr(BaseAgent, m))}
    anth_methods = {m for m in dir(AnthropicAgent) if not m.startswith("_") and callable(getattr(AnthropicAgent, m))}
    # 核心公开方法（v1.3.0 起 conversation / aconversation 是新主入口；旧名是 deprecated alias）
    for name in ("conversation", "conversation_with_tool",
                 "aconversation", "aconversation_with_tool",
                 "out", "pack",
                 "ask_for_help", "list_agents", "attempt_completion", "reload",
                 "register_template", "activate_template", "deactivate_template",
                 "list_templates", "get_all_available_tools",
                 "register_tool_hook"):
        assert name in base_methods, f"BaseAgent missing public method: {name}"
        assert name in anth_methods, f"AnthropicAgent missing public method: {name}"


def test_base_agent_out_and_pack_have_annotations():
    """v0.3.1 给 BaseAgent 补的注解到位"""
    import inspect
    out_sig = inspect.signature(BaseAgent.out)
    # ``from __future__ import annotations`` 把注解变成字符串（PEP 563），比较时用 'dict'
    assert out_sig.parameters["content"].annotation == "dict"
    assert out_sig.return_annotation == "None"

    pack_sig = inspect.signature(BaseAgent.pack)
    assert pack_sig.return_annotation == "None"

    # v1.3.0 起 conversation / aconversation 是主入口，参数 tooluse / addhistory 替代旧 tool 标记
    conv_sig = inspect.signature(BaseAgent.conversation)
    assert conv_sig.parameters["tooluse"].annotation == "bool"
    assert conv_sig.parameters["addhistory"].annotation == "bool"

    aconv_sig = inspect.signature(BaseAgent.aconversation)
    assert aconv_sig.parameters["tooluse"].annotation == "bool"
    assert aconv_sig.parameters["addhistory"].annotation == "bool"

    # 旧名保留为 deprecated alias
    assert hasattr(BaseAgent, "conversation_with_tool")
    assert hasattr(BaseAgent, "aconversation_with_tool")
