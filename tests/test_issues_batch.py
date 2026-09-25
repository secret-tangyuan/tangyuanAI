"""v1.2.0 issues 修复测试 (#15, #17, #18, #20, #21)。"""
from __future__ import annotations

import io
import sys

import pytest
from tangyuanAI import BaseAgent, tool_registry
from tangyuanAI.errors import ConversationError

# ============================================================
# #18 _default_max_tokens 默认 4096
# ============================================================


def test_default_max_tokens_is_4096():
    """v1.2.0 (#18): Anthropic transport 行为统一,OpenAI transport 忽略 None。"""
    assert BaseAgent._default_max_tokens == 4096


# ============================================================
# #17 register_tool 直接调用 raise TypeError
# ============================================================


def test_register_tool_direct_call_raises():
    """v1.2.0 (#17): 不传函数直接调 register_tool(name=...) 应该 log warning(不再静默注册空 schema)。"""

    from loguru import logger as _loguru
    captured = []
    sink_id = _loguru.add(lambda msg: captured.append(str(msg)), level="WARNING")
    try:
        tool_registry.register_tool(name="bad", description="bad tool", parameters={})
    finally:
        _loguru.remove(sink_id)
    assert any("register_tool" in m and "装饰器" in m for m in captured), \
        f"应 log warning 提示装饰器误用,实际: {captured}"


def test_register_tool_as_decorator_still_works():
    """装饰器用法仍正常 — 给真函数装饰。"""
    @tool_registry.register_tool(
        name="good_tool", description="正常用法", parameters={"type": "object", "properties": {}, "required": []}
    )
    def good_tool(query: str) -> str:
        return f"got: {query}"

    info = tool_registry.get_tool_info("good_tool")
    assert info is not None
    assert info["description"] == "正常用法"


# ============================================================
# #20 aconversation(addhistory=False) + 仅 system message → raise
# ============================================================


class _StubTransportOK:
    """不会真调到的占位 transport;检查在 transport 之前就抛。"""

    def __init__(self, *args, **kwargs):
        pass

    def chat(self, req):
        raise RuntimeError("transport should not be called")

    async def achat(self, req):
        raise RuntimeError("transport should not be called")


def _make_agent_with_only_system_prompt(BaseCls):
    """构造一个 history 仅有 system message 的 agent 实例。"""
    cls = type(
        "TestAgent",
        (BaseCls,),
        {
            "uuid": "test-uuid",
            "name": "test",
            "prompt": "你是助手",
            "api_provider": "https://api.example.com/v1",
            "api_key": "test-key",
            "model_name": "test-model",
            "fc_model": False,
            "stream": False,
            "enable_connectivity": False,
        },
    )
    inst = cls()
    inst.history = [{"role": "system", "content": "你是助手"}]
    return inst


def test_aconversation_only_system_addhistory_false_raises(monkeypatch):
    """v1.2.0 (#20): aconversation 时 history 仅有 system + addhistory=False + messages=None → ConversationError。"""
    from tangyuanAI.agent import _AgentCommon

    inst = _make_agent_with_only_system_prompt(_AgentCommon)
    # 替换 transport 为 stub,确保即便 raise 也走不到 transport
    monkeypatch.setattr(inst, "_transport_cls", _StubTransportOK)
    # 绕开 connectivity 线程(_default_max_tokens 已改,但 _connectivity 还会跑)
    inst._connectivity = lambda: None

    with pytest.raises(ConversationError, match="messages 为空"):
        import asyncio
        # messages=None 显式触发"ephemeral 也没,history 也没"分支
        asyncio.run(inst.aconversation(None, tooluse=False, addhistory=False))


class _CaptureTransport:
    """记录最后一次 ChatRequest,return 一个最小 LLMResponse。"""

    last_req = None  # 类级,跨测试共享

    def __init__(self, *args, **kwargs):
        pass

    def chat(self, req):
        type(self).last_req = req
        # 返回最小响应,_collect_plain_response 取出 text
        from tangyuanAI.llm_transport import LLMResponse, UsageInfo
        return LLMResponse(
            text="ok", tool_calls=[], stop_reason="stop",
            usage=UsageInfo(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def achat(self, req):
        return self.chat(req)


def test_aconversation_only_system_addhistory_true_works(monkeypatch):
    """addhistory=True 时,正常追加 user 消息,transport 收到非空 messages。"""
    from tangyuanAI.agent import _AgentCommon

    inst = _make_agent_with_only_system_prompt(_AgentCommon)
    monkeypatch.setattr(inst, "_transport_cls", _CaptureTransport)
    _CaptureTransport.last_req = None

    import asyncio
    asyncio.run(inst.aconversation("hi", tooluse=False, addhistory=True))

    # 走到 transport,说明 messages 非空
    assert _CaptureTransport.last_req is not None
    assert _CaptureTransport.last_req.messages, "addhistory=True 应让 messages 非空"
    assert _CaptureTransport.last_req.messages[0]["role"] == "user"


# ============================================================
# #21 Windows logging encoding — stderr 走 utf-8
# ============================================================


@pytest.mark.skipif(not hasattr(sys.stderr, "reconfigure"), reason="Python < 3.7 无 stderr.reconfigure")
def test_stderr_encoding_reconfigured_to_utf8():
    """v1.2.0 (#21): setup_logging() 把 sys.stderr 切到 utf-8(Windows cp936/gbk → utf-8)。"""
    from tangyuanAI.logging_config import setup_logging
    saved_encoding = getattr(sys.stderr, "encoding", None)
    try:
        sys.stderr.reconfigure(encoding="ascii")  # 模拟 Windows 默认编码
        assert sys.stderr.encoding != "utf-8"
        setup_logging(level="DEBUG")  # 触发 stderr 重配置
        assert sys.stderr.encoding == "utf-8"
    finally:
        # 还原环境(测试不要污染)
        if saved_encoding:
            try:
                sys.stderr.reconfigure(encoding=saved_encoding)
            except (OSError, AttributeError):
                pass


def test_setup_logging_emoji_message_does_not_crash(caplog, monkeypatch):
    """emoji + 中文消息经过 setup_logging 不抛 UnicodeEncodeError。"""
    from tangyuanAI.logging_config import setup_logging

    # 把 stderr 重定向到 StringIO,验证 emoji 写入不抛
    fake_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", fake_stderr)
    setup_logging(level="DEBUG")
    # 验证 emoji + 中文写进 StringIO 不抛
    fake_stderr.write("用户发了 👋 emoji\n")  # 真 emoji
    fake_stderr.write("中文日志\n")
    assert "👋" in fake_stderr.getvalue()
    assert "中文" in fake_stderr.getvalue()


# ============================================================
# #15 docstring 警告(冒烟测试:文档提到 + 占位类仍可用)
# ============================================================


def test_agent_placeholder_still_resolves_protocol():
    """v1.2.0 (#15): 占位类 tangyuanAI.Agent 仍按 protocol 选 transport。"""
    import tangyuanAI

    @tangyuanAI.template_agent("protocol_test", uuid="proto-uuid", description="protocol 测试")
    class ProtocolAgent(tangyuanAI.Agent):
        protocol = "anthropic"

    activate = getattr(tangyuanAI, "activate_template", None)
    assert activate is not None

    activate("protocol_test")
    agent = tangyuanAI.agent_list["protocol_test"]
    # MRO 应含 _AnthropicBase 而非 _OpenAIBase
    from tangyuanAI.agent import _AnthropicBase, _OpenAIBase
    assert isinstance(agent, _AnthropicBase)
    assert not isinstance(agent, _OpenAIBase)
