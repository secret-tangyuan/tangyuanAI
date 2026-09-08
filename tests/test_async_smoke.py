# -*- coding: utf-8 -*-
"""
异步路径冒烟测试

不动真实 LLM，只验证：
1. async/await 语法 OK
2. agent 类的 ``aconversation`` 方法（v1.3.0 新主入口）和旧名 ``aconversation_with_tool``（deprecated alias）都存在且可调用
3. 简单的 async 工具执行能工作
"""
import asyncio

import pytest
from tangyuanAI.Agent_Base_ import Agent as BaseAgent
from tangyuanAI.anthropic_agent import AnthropicAgent


def test_anthropic_agent_has_aconversation():
    """AnthropicAgent 有 async 版主对话入口（v1.3.0 新主入口 + 旧 deprecated alias）"""
    assert hasattr(AnthropicAgent, "aconversation")
    assert asyncio.iscoroutinefunction(AnthropicAgent.aconversation)
    assert hasattr(AnthropicAgent, "aconversation_with_tool")
    assert asyncio.iscoroutinefunction(AnthropicAgent.aconversation_with_tool)


def test_base_agent_has_aconversation():
    """BaseAgent 有 async 版主对话入口（v1.3.0 新主入口 + 旧 deprecated alias）"""
    assert hasattr(BaseAgent, "aconversation")
    assert asyncio.iscoroutinefunction(BaseAgent.aconversation)
    assert hasattr(BaseAgent, "aconversation_with_tool")
    assert asyncio.iscoroutinefunction(BaseAgent.aconversation_with_tool)


@pytest.mark.asyncio
async def test_async_simple_tool_runs():
    """ToolRunner 异步路径：await submit 也能跑（同步线程池）"""
    from tangyuanAI.tool_runner import ToolRunner

    runner = ToolRunner(timeout=1.0)
    try:
        # 异步代码里调同步 submit
        result, async_id = runner.submit(lambda x: x * 2, 21)
        assert result == 42
        assert async_id is None
    finally:
        runner.shutdown()


def test_async_http_client_constructor():
    """AsyncHTTPClient 可以直接构造（无需 async context）"""
    from tangyuanAI.http_utils import AsyncHTTPClient

    client = AsyncHTTPClient(default_timeout=5.0)
    assert client.default_timeout == 5.0
