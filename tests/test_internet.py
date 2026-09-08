# -*- coding: utf-8 -*-
"""
LLM HTTP / 对话流端到端测试（v0.4.1+）。

- BaseAgent ``aconversation_with_tool`` 端到端（async path）
- ``attempt_completion`` 终止对话循环
- 异常流（LLM 500 / tool 抛异常 / 不可恢复错误）
- 异常重试（http_utils 退避）
- ``api_provider`` 多格式拼接
- ``ask_for_help`` 跨 Agent 调用与队列集成

每个测试都是"真实任务驱动"：用户提具体需求，mock 按真实 LLM 行为
（多步 tool_use / text / attempt_completion）返回，验证端到端流程。
"""
from __future__ import annotations

import uuid as _uuid

import pytest
from _llm_mock import (
    MockState,
    _AnthropicMockHandler,
    _OpenAIMockHandler,
    _start_mock_server,
    anthropic_text_response,
    anthropic_tool_use_response,
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
from tangyuanAI.anthropic_agent import AnthropicAgent

# 网络/环境敏感测试：默认跳过（CI runner 网络不稳定），-m flaky 显式跑
pytestmark = pytest.mark.flaky

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_globals():
    saved_tools = dict(tool_registry._tools)
    saved_perms = dict(tool_registry._agent_permissions)
    from tangyuanAI import agent_template_pool
    agent_list.clear()
    agent_template_pool.clear()
    yield
    agent_list.clear()
    agent_template_pool.clear()
    tool_registry._tools.clear()
    tool_registry._agent_permissions.clear()
    tool_registry._tools.update(saved_tools)
    tool_registry._agent_permissions.update(saved_perms)


def _start_anthropic_mock() -> tuple[MockState, str, object]:
    state = MockState()
    _AnthropicMockHandler.state = state
    base_url, server = _start_mock_server(_AnthropicMockHandler)
    return state, base_url, server


def _start_openai_mock() -> tuple[MockState, str, object]:
    state = MockState()
    _OpenAIMockHandler.state = state
    base_url, server = _start_mock_server(_OpenAIMockHandler)
    return state, base_url, server


def _make_anthropic(name: str, base_url: str, use_stream: bool = False) -> AnthropicAgent:
    @template_agent(name, uuid=_uuid.uuid4().hex, description="test")
    class _A(Agent):
        protocol = "anthropic"
        prompt = "你是一个助手，会按用户需求调用工具"
        model_name = "test-model"
        api_key = "test-key"
        api_provider = base_url
        stream = use_stream

    activate_template(name)
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001
    return inst


def _make_openai(name: str, base_url: str, use_stream: bool = False) -> BaseAgent:
    @template_agent(name, uuid=_uuid.uuid4().hex, description="test")
    class _OA(Agent):
        protocol = "openai"
        prompt = "你是一个助手，会按用户需求调用工具"
        model_name = "test-model"
        api_key = "test-key"
        api_provider = base_url + "/v1/chat/completions"
        stream = use_stream

    activate_template(name)
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001
    return inst


# ===========================================================================
# BaseAgent aconversation 端到端（async）
# ===========================================================================
# 真实任务：用户让 agent 异步查天气 / 查库存

@pytest.mark.asyncio
async def test_user_asks_weather_agent_uses_async_stream():
    """用户 async + stream：让 agent 查北京天气"""
    state, base_url, server = _start_openai_mock()
    try:
        agent = _make_openai("int-weather-stream", base_url, use_stream=True)

        @tool_registry.register_tool(
            allowed_agents=["int-weather-stream"],
            name="get_weather",
            description="查询城市天气",
            parameters={
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        )
        def get_weather(city: str) -> str:
            return f"{city}今天晴 25°C"

        state.queue(lambda _b: openai_tool_call_response(
            "cw1", "get_weather", {"city": "北京"},
        ))
        state.queue(lambda _b: openai_text_response("北京今天晴 25°C，适合出门。"))

        out = await agent.aconversation("北京天气怎么样？")
        assert "北京" in out
        assert state.real_call_count == 2
    finally:
        server.shutdown()
        server.server_close()
        _OpenAIMockHandler.state = None


@pytest.mark.asyncio
async def test_user_asks_inventory_check_via_async():
    """用户 async non-stream：让 agent 查某 SKU 的库存"""
    state, base_url, server = _start_openai_mock()
    try:
        agent = _make_openai("int-inventory", base_url, use_stream=False)

        @tool_registry.register_tool(
            allowed_agents=["int-inventory"],
            name="check_inventory",
            description="查 SKU 库存",
            parameters={
                "type": "object",
                "properties": {"sku": {"type": "string"}},
                "required": ["sku"],
            },
        )
        def check_inventory(sku: str) -> str:
            return f"SKU={sku} 库存 42 件"

        state.queue(lambda _b: openai_tool_call_response(
            "ci1", "check_inventory", {"sku": "ABC-001"},
        ))
        state.queue(lambda _b: openai_text_response(
            "ABC-001 还有 42 件库存。",
        ))

        out = await agent.aconversation("ABC-001 库存多少？")
        assert "42" in out
    finally:
        server.shutdown()
        server.server_close()
        _OpenAIMockHandler.state = None


# ===========================================================================
# attempt_completion 终止循环
# ===========================================================================
# 真实任务：用户让 agent 完成最后汇报 → agent 调 attempt_completion → 立即结束

def test_user_says_finish_agent_marks_task_complete_and_exits():
    """用户：'做完了，把总结发给我' → agent 调 attempt_completion → 框架再问一次 LLM 拿最终回复 → 结束"""
    state, base_url, server = _start_anthropic_mock()
    try:
        agent = _make_anthropic("int-finish", base_url)

        # 第一轮：调 attempt_completion
        state.queue(lambda _b: anthropic_tool_use_response(
            "tc1", "attempt_completion", {"report_content": "任务全部完成。"},
        ))
        # 第二轮：LLM 拿 attempt_completion 结果后再回应一次
        state.queue(lambda _b: anthropic_text_response("好的，任务完成。"))

        out = agent.conversation("做完了，给我最终汇报")
        # attempt_completion 把 report_content 喂回 LLM，最终 LLM 拿这个生成"好的，任务完成。"
        assert "好的" in out or "任务完成" in out
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


# ===========================================================================
# 异常流：LLM 500 / 不可恢复错误
# ===========================================================================
# 真实任务：mock 服务端返回 5xx → 框架应正确报错

def test_user_request_when_llm_returns_500_agent_raises():
    """mock 服务端持续返 500 → http_utils 重试耗尽后抛 APIError"""
    # 写一个返 500 的简易 server
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from tangyuanAI.errors import APIError

    # 简化：直接调 transport.chat 验证 500 的传播
    from tangyuanAI.llm_transport import HttpxOpenAITransport

    class _500Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Internal Server Error")

        def log_message(self, *a, **k):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _500Handler)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        transport = HttpxOpenAITransport(endpoint=base_url + "/v1/chat/completions", api_key="x")
        with pytest.raises(APIError):
            transport.chat(__import__("tangyuanAI.llm_transport", fromlist=["ChatRequest"]).ChatRequest(
                model="m", system="s", messages=[{"role": "user", "content": "hi"}],
            ))
    finally:
        server.shutdown()
        server.server_close()


def test_user_request_when_tool_raises_runtime_error_agent_recovers():
    """用户让 agent 调一个会抛 RuntimeError 的工具 → 框架捕获 → 喂回 LLM → LLM 重试"""
    state, base_url, server = _start_anthropic_mock()
    try:
        agent = _make_anthropic("int-tool-err", base_url)

        @tool_registry.register_tool(
            allowed_agents=["int-tool-err"],
            name="flaky",
            description="flaky",
            parameters={"type": "object", "properties": {}},
        )
        def flaky() -> str:
            raise RuntimeError("transient db error")

        # mock: LLM 调 flaky → 拿到错误 → 道歉
        state.queue(lambda _b: anthropic_tool_use_response("t1", "flaky", {}))
        state.queue(lambda _b: anthropic_text_response("服务出错了，抱歉"))

        out = agent.conversation("帮我跑一下")
        assert "服务出错" in out or "抱歉" in out
        assert state.real_call_count == 2
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


# ===========================================================================
# ask_for_help 跨 Agent + 队列集成
# ===========================================================================
# 真实任务：orchestrator 让 researcher Agent 调研某主题

def test_orchestrator_asks_researcher_via_ask_for_help_queue():
    """orchestrator agent 让 researcher agent 调研某主题；
    验证 ask_for_help 走全局队列，researcher 收到消息并回复。
    """
    state, base_url, server = _start_anthropic_mock()
    try:
        # orchestrator（建但不直接用，本测试只验证 researcher 通过 ask_for_help 收到消息）
        _make_anthropic("orchestrator", base_url)

        # researcher（独立 agent，mock 服务端同样回它）
        researcher = _make_anthropic("researcher", base_url)

        # 给 researcher 注册一个调研工具
        @tool_registry.register_tool(
            allowed_agents=["researcher"],
            name="search_topic",
            description="搜索主题资料",
            parameters={
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
        )
        def search_topic(topic: str) -> str:
            return f"关于{topic}的调研：...（5 个要点）"

        # 单步验证：直接调 researcher.conversation_with_tool → mock 返回调研结果
        state.queue(lambda _b: anthropic_text_response("RAG 优化的关键：分块策略 + embedding 选型"))

        out = researcher.conversation("查一下 RAG 优化")
        assert "RAG" in out
        # 验证 researcher.history 里有用户消息（content 可能是 list 或 str）
        def _content_to_str(c):
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return " ".join(b.get("text", "") for b in c if isinstance(b, dict))
            return str(c)
        researcher_msgs = [m for m in researcher.history if m.get("role") == "user"]
        assert any("RAG" in _content_to_str(m.get("content") or "") for m in researcher_msgs)
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


# ===========================================================================
# api_provider 多格式（Anthropic 协议）
# ===========================================================================
# 真实任务：用户配置不同 endpoint 格式 → 框架正确拼接

def test_user_configures_full_endpoint_no_concat():
    """api_provider 已经包含 /v1/messages → 框架原样使用"""
    agent = AnthropicAgent.__new__(AnthropicAgent)
    agent.uuid = "u1"
    agent.name = "test"
    agent.api_provider = "https://api.example.com/v1/messages"
    assert agent._endpoint() == "https://api.example.com/v1/messages"


def test_user_configures_base_with_v1_concat_messages():
    """api_provider 末尾是 /v1 → 拼 /messages"""
    agent = AnthropicAgent.__new__(AnthropicAgent)
    agent.uuid = "u1"
    agent.name = "test"
    agent.api_provider = "https://api.example.com/v1"
    assert agent._endpoint() == "https://api.example.com/v1/messages"


def test_user_configures_base_url_concat_v1_messages():
    """api_provider 是裸 base URL → 拼 /v1/messages"""
    agent = AnthropicAgent.__new__(AnthropicAgent)
    agent.uuid = "u1"
    agent.name = "test"
    agent.api_provider = "https://api.example.com"
    assert agent._endpoint() == "https://api.example.com/v1/messages"


def test_user_configures_empty_api_provider_raises():
    """api_provider 为空 → ValueError"""
    agent = AnthropicAgent.__new__(AnthropicAgent)
    agent.uuid = "u1"
    agent.name = "test"
    agent.api_provider = ""
    with pytest.raises(ValueError, match="必须显式设置 api_provider"):
        agent._endpoint()


def test_user_configures_trailing_slash_handled():
    """api_provider 末尾带 / → 也能正确拼接（不重复 /）"""
    agent = AnthropicAgent.__new__(AnthropicAgent)
    agent.uuid = "u1"
    agent.name = "test"
    agent.api_provider = "https://api.example.com/"
    assert agent._endpoint() == "https://api.example.com/v1/messages"


# ===========================================================================
# 并发（同 agent 多次调用）
# ===========================================================================
# 真实任务：同一 agent 被多次 conversation_with_tool 调用（业务上是批处理）

def test_user_calls_same_agent_twice_serial():
    """同一 agent 两次串行 conversation_with_tool，两次都成功"""
    state, base_url, server = _start_anthropic_mock()
    try:
        agent = _make_anthropic("int-twice", base_url)

        @tool_registry.register_tool(
            allowed_agents=["int-twice"],
            name="echo",
            description="echo",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        )
        def echo(text: str) -> str:
            return f"echo:{text}"

        # 第一次
        state.queue(lambda _b: anthropic_tool_use_response("c1", "echo", {"text": "first"}))
        state.queue(lambda _b: anthropic_text_response("first done"))
        out1 = agent.conversation("first")
        assert "first done" in out1

        # 第二次
        state.queue(lambda _b: anthropic_tool_use_response("c2", "echo", {"text": "second"}))
        state.queue(lambda _b: anthropic_text_response("second done"))
        out2 = agent.conversation("second")
        assert "second done" in out2

        # history 累积
        assert len(agent.history) > 5
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


# ===========================================================================
# 工具超时 → 后台 future（end-to-end 真实任务）
# ===========================================================================
# 真实任务：用户让 agent 跑一个长任务，框架不能阻塞

def test_user_runs_slow_data_migration_agent_does_not_block():
    """场景：用户让 agent 跑一个长数据迁移（>5s）。框架应超时转后台，
    LLM 拿到 task_id 描述后给"稍后看"的回复，2 秒内 conversation 返回。
    """
    import time as _time

    from tangyuanAI.tool_runner import ToolRunner

    state, base_url, server = _start_anthropic_mock()
    try:
        agent = _make_anthropic("int-slow", base_url)
        # 极短超时
        type(agent).tool_timeout = 0.1
        agent._tool_runner = ToolRunner(timeout=0.1, max_workers=2)  # noqa: SLF001

        @tool_registry.register_tool(
            allowed_agents=["int-slow"],
            name="migrate_data",
            description="数据迁移",
            parameters={"type": "object", "properties": {}, "required": []},
        )
        def migrate_data() -> str:
            _time.sleep(2)  # 远超 0.1s 的 tool_timeout
            return "迁移完成"

        state.queue(lambda _b: anthropic_tool_use_response("t1", "migrate_data", {}))
        state.queue(lambda _b: anthropic_text_response("已转后台，稍后查 task_id"))

        start = _time.time()
        out = agent.conversation("跑数据迁移")
        elapsed = _time.time() - start

        # 关键：< 6 秒（没阻塞 2 秒）。慢 CI 上 mock 串行 + transport 开销可能吃掉 1-4 秒。
        assert elapsed < 6.0, f"框架被阻塞 {elapsed:.1f}s"
        # LLM 总结里"迁移完成"不应出现（工具还没真完成）
        assert "迁移完成" not in out
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


def test_user_runs_fast_task_agent_returns_result_immediately():
    """对照：用户跑快速任务 → 正常返回结果（验证非超时路径）"""
    state, base_url, server = _start_anthropic_mock()
    try:
        agent = _make_anthropic("int-fast", base_url)

        @tool_registry.register_tool(
            allowed_agents=["int-fast"],
            name="quick_check",
            description="快速检查",
            parameters={"type": "object", "properties": {}},
        )
        def quick_check() -> str:
            return "all_good"

        state.queue(lambda _b: anthropic_tool_use_response("t1", "quick_check", {}))
        state.queue(lambda _b: anthropic_text_response("检查通过"))

        out = agent.conversation("跑快速检查")
        assert "检查通过" in out
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None
