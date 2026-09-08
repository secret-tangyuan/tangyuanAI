# -*- coding: utf-8 -*-
"""
A2A 兼容层测试（tests/test_a2a.py，核心原生）
=====================================

验证 #6：
- 协议层：JSON-RPC 构造/解析、Agent Card、文本提取
- 客户端：discover + register_a2a_agent（mock HTTP）
- 导出：A2AExporter.app()（aiohttp test client）
- source 跟踪：internal / a2a:<url> 区分
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tangyuanAI import a2a_protocol
from tangyuanAI.a2a_client import A2AAgentProxy, register_a2a_agent

# ---------------------------------------------------------------------------
# 协议层
# ---------------------------------------------------------------------------

class TestProtocol:
    def test_json_rpc_request(self):
        req = a2a_protocol.make_json_rpc_request("tasks/send", {"id": "t1"}, rpc_id="r1")
        assert req["jsonrpc"] == "2.0"
        assert req["method"] == "tasks/send"
        assert req["id"] == "r1"

    def test_json_rpc_response(self):
        resp = a2a_protocol.make_json_rpc_response({"ok": True}, "r1")
        assert resp["result"] == {"ok": True}

    def test_json_rpc_error(self):
        err = a2a_protocol.make_json_rpc_error(-32601, "unknown method", "r1")
        assert err["error"]["code"] == -32601

    def test_parse_valid(self):
        req = a2a_protocol.parse_json_rpc({"jsonrpc": "2.0", "id": "1", "method": "m"})
        assert req["method"] == "m"

    def test_parse_invalid(self):
        with pytest.raises(ValueError):
            a2a_protocol.parse_json_rpc({"method": "m"})  # 缺 jsonrpc
        with pytest.raises(ValueError):
            a2a_protocol.parse_json_rpc({"jsonrpc": "2.0"})  # 缺 method

    def test_agent_card(self):
        card = a2a_protocol.make_agent_card("w", "writer", "http://h:9000/a2a/v1")
        assert card["name"] == "w"
        assert "protocolVersion" in card

    def test_text_message_and_extract(self):
        msg = a2a_protocol.make_text_message("hi")
        assert msg["parts"][0]["text"] == "hi"
        out = a2a_protocol.extract_text_from_artifacts(
            [{"parts": [{"kind": "text", "text": "hello"}]}]
        )
        assert out == "hello"


# ---------------------------------------------------------------------------
# 客户端（导入方向）
# ---------------------------------------------------------------------------

class TestClient:
    @patch("tangyuanAI.a2a_client.AsyncHTTPClient")
    async def test_discover(self, MockClient):
        fake_resp = MagicMock()
        fake_resp.json.return_value = {"name": "remote", "description": "远端"}
        mock_instance = MagicMock()
        mock_instance.aget = AsyncMock(return_value=fake_resp)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        MockClient.return_value = mock_instance

        from tangyuanAI.a2a_client import discover
        got = await discover("http://host:9000")
        assert got["name"] == "remote"
        # 验证走了 aget（不再走 httpx raw）
        mock_instance.aget.assert_awaited_once()
        called_url = mock_instance.aget.await_args.args[0]
        assert called_url == "http://host:9000/.well-known/agent.json"

    def test_proxy_conversation(self):
        """A2AAgentProxy.conversation_with_tool 转发到远端（mock send_task_sync）。"""
        proxy = A2AAgentProxy(name="a2a_remote", url="http://host:9000", description="远端")
        assert proxy.source == "a2a:http://host:9000"
        with patch("tangyuanAI.a2a_client.send_task_sync", return_value={
            "artifacts": [{"parts": [{"kind": "text", "text": "远端回复"}]}]
        }):
            reply = proxy.conversation_with_tool("你好")
        assert reply == "远端回复"

    @patch("tangyuanAI.a2a_client.discover")
    @patch("tangyuanAI.Agent_list.register_agent")
    def test_register_a2a_agent(self, mock_reg, mock_discover):
        """register_a2a_agent 发现 + 注册，source 标记 a2a:<url>。"""
        mock_discover.return_value = {"name": "git", "description": "git agent", "skills": []}
        proxy = register_a2a_agent("http://host:9000")
        assert isinstance(proxy, A2AAgentProxy)
        assert proxy.name == "a2a_git"
        # register_agent 被调用，source 参数传对了
        call_kwargs = mock_reg.call_args
        assert call_kwargs[0][0] == "a2a_git"
        assert call_kwargs[0][1] is proxy
        assert call_kwargs[1]["source"] == "a2a:http://host:9000"


# ---------------------------------------------------------------------------
# 导出（aiohttp test client）
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    __import__("importlib.util").util.find_spec("aiohttp") is None,
    reason="aiohttp not installed",
)
class TestExporter:
    @pytest.fixture
    def fake_agent(self):
        class FakeAgent:
            name = "writer"
            description = "写作 agent"
            def conversation(self, prompt, **kw):
                return f"写好了: {prompt}"

        return FakeAgent()

    @pytest.mark.asyncio
    async def test_agent_card_endpoint(self, fake_agent):
        from aiohttp.test_utils import TestClient, TestServer
        from tangyuanAI.a2a_exporter import A2AExporter

        exporter = A2AExporter(agent_list={"writer": fake_agent}, port=9001)
        app = exporter.app()
        server = TestServer(app)

        async with TestClient(server) as client:
            resp = await client.get("/.well-known/agent.json")
            assert resp.status == 200
            card = await resp.json()
            assert "writer" in [a["name"] for a in card.get("agents", [])]

    @pytest.mark.asyncio
    async def test_tasks_send(self, fake_agent):
        from aiohttp.test_utils import TestClient, TestServer
        from tangyuanAI.a2a_exporter import A2AExporter
        from tangyuanAI.a2a_protocol import make_json_rpc_request, make_text_message

        exporter = A2AExporter(agent_list={"writer": fake_agent}, port=9001)
        app = exporter.app()
        server = TestServer(app)

        body = make_json_rpc_request(
            "tasks/send",
            {"id": "t1", "message": make_text_message("写个标题")},
        )
        async with TestClient(server) as client:
            resp = await client.post("/a2a/v1/tasks/send", json=body)
            assert resp.status == 200
            data = await resp.json()
            assert data["result"]["status"]["state"] == "completed"
            text = a2a_protocol.extract_text_from_artifacts(data["result"]["artifacts"])
            assert "写个标题" in text


# ---------------------------------------------------------------------------
# source 跟踪
# ---------------------------------------------------------------------------

class TestSourceTracking:
    def test_internal_vs_external(self, monkeypatch):
        from tangyuanAI import Agent_list as al

        class FakeAgent:
            name = "x"

        al.register_agent("internal_agent", FakeAgent())  # 默认 internal
        al.register_agent("a2a_git", FakeAgent(), source="a2a:http://host:9000")

        assert al.agent_source("internal_agent") == "internal"
        assert al.agent_source("a2a_git") == "a2a:http://host:9000"
        assert "internal_agent" in al.list_internal_agents()
        assert "a2a_git" in al.list_external_agents()
        assert ("internal_agent", "internal") in al.list_agents_with_source()

        # 清理
        al.unregister_agent("internal_agent")
        al.unregister_agent("a2a_git")
