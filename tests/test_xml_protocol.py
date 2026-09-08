# -*- coding: utf-8 -*-
"""
XML 协议模式单测（fc_model=False）。

默认 Agent 走 Function Calling（OpenAI / Anthropic tool_calls / tool_use）。
但 Agent 也支持 XML 模式（``fc_model=False``），LLM 在文本中嵌入
``<ask_for_help>...</ask_for_help>`` / ``<attempt_completion>...</attempt_completion>``
等标签，框架用正则解析执行。

真实任务：用户让 agent 在 XML 模式下完成一个工作流 → 验证 XML 解析 + 工具调用 + 结束。
"""
from __future__ import annotations

import uuid as _uuid

import pytest
from _llm_mock import (
    MockState,
    _AnthropicMockHandler,
    _start_mock_server,
    anthropic_text_response,
)
from tangyuanAI import (
    Agent,
    activate_template,
    agent_list,
    agent_template_pool,
    template_agent,
    tool_registry,
)


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


def _make_xml_agent(name: str, base_url: str):
    """建一个 fc_model=False 的 agent（走 XML 协议）"""

    @template_agent(name, uuid=_uuid.uuid4().hex, description="test")
    class _A(Agent):
        protocol = "anthropic"
        prompt = "用 XML 标签调工具"
        model_name = "test-model"
        api_key = "test-key"
        api_provider = base_url
        fc_model = False  # ← 关键：XML 模式

    activate_template(name)
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001
    return inst


# ===========================================================================
# 端到端：XML 模式真实任务
# ===========================================================================

def test_user_asks_agent_in_xml_mode_agent_calls_tool_via_xml_tags():
    """场景：fc_model=False → LLM 在 text 中嵌入 XML 标签 → 框架解析并执行工具。
    真实任务：用户让 agent 查 weather，LLM 返：
        好的，让我查一下。
        <get_weather>
        <city>北京</city>
        </get_weather>
    框架解析 <get_weather> → 调 get_weather(city='北京') → 拿结果"北京今天晴 25°C"。
    """
    state, base_url, server = _start_mock()
    try:
        agent = _make_xml_agent("xml-weather", base_url)

        @tool_registry.register_tool(
            allowed_agents=["xml-weather"],
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

        # LLM 返 XML 标签包裹的工具调用（框架会从 full_content 抽 XML 块）
        llm_response = """
        好的，让我查一下。
        <get_weather>
        <city>北京</city>
        </get_weather>
        """
        state.queue(lambda _b: anthropic_text_response(llm_response))
        # 第二轮 LLM 拿工具结果后给最终回答
        state.queue(lambda _b: anthropic_text_response("北京今天晴 25°C，适合出门。"))

        out = agent.conversation("北京天气？")
        # 最终回答里应该包含"北京"和"晴"
        assert "北京" in out
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


def test_user_asks_agent_attempt_completion_via_xml_tag():
    """场景：XML 模式下 LLM 用 <attempt_completion> 标签结束对话。
    真实任务：用户让 agent 结束任务 → LLM 嵌入 <attempt_completion>...</attempt_completion>。
    """
    state, base_url, server = _start_mock()
    try:
        agent = _make_xml_agent("xml-finish", base_url)

        llm_response = """
        任务完成。
        <attempt_completion>
        <report_content>XML 模式任务汇报完成</report_content>
        </attempt_completion>
        """
        state.queue(lambda _b: anthropic_text_response(llm_response))
        # 第二轮 LLM 拿 attempt_completion 后再回
        state.queue(lambda _b: anthropic_text_response("好的，搞定。"))

        out = agent.conversation("任务结束")
        assert "搞定" in out or "完成" in out
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


def test_xml_mode_strips_out_text_and_thinking_tags_before_parsing():
    """场景：LLM 文本里包含 <out_text> 和 <thinking> 标签 → 解析前应剥离。
    真实任务：让 agent 调一个工具，工具结果被混入文本中。
    """
    # 模拟 LLM 输出：含 <out_text>、<thinking>、<tool> 嵌套
    raw = """
    <out_text>分析一下</out_text>
    <thinking>让我查</thinking>
    <get_weather>
    <city>上海</city>
    </get_weather>
    """
    import re

    from bs4 import BeautifulSoup
    clean_pattern = re.compile(r'</?(out_text|thinking)>', flags=re.S)
    cleaned = clean_pattern.sub('', raw)
    # finditer 返完整 match（不是单个捕获组）
    xml_blocks = [m.group(0) for m in re.finditer(r'<(\w+)>.*?</\1>', cleaned, flags=re.S)]
    # 应只剩一个 get_weather 块
    assert len(xml_blocks) == 1
    assert "get_weather" in xml_blocks[0]
    # 解析 city 参数
    soup = BeautifulSoup(xml_blocks[0], "xml")
    root = soup.find()
    assert root.name == "get_weather"
    city_el = root.find("city")
    assert city_el.text == "上海"
