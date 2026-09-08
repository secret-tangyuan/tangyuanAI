# -*- coding: utf-8 -*-
"""
A2A Exporter（kb/a2a_exporter.py）
==================================

**导出方向**：把本地 tangyuanAI agent_list 中的 agent 暴露为 A2A HTTP endpoint，
让外部 A2A 客户端可发现（`/.well-known/agent.json`）并调用（`/a2a/v1/tasks/send`）。

**依赖**：`aiohttp`（optional，仅导出时需要）。未装 aiohttp 时 `app()` / `serve()` 报清晰错误。

**用法**：
```python
from tangyuanAI.a2a_exporter import A2AExporter

exporter = A2AExporter(host="127.0.0.1", port=9000)  # 默认用全局 agent_list
# 或指定 agent 子集
exporter = A2AExporter(agent_list={"writer": writer_agent})

await exporter.serve()  # 阻塞
```

**外部 A2A 客户端**：
```bash
curl http://127.0.0.1:9000/.well-known/agent.json
curl -X POST http://127.0.0.1:9000/a2a/v1/tasks/send \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":"1","method":"tasks/send",
       "params":{"id":"t1","message":{"role":"user",
                "parts":[{"kind":"text","text":"你好"}]}}}'
```
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from tangyuanAI.logging_config import logger

__all__ = ["A2AExporter"]


class A2AExporter:
    """把本地 agent_list 暴露为 A2A HTTP endpoint。"""

    def __init__(
        self,
        agent_list: Optional[dict[str, Any]] = None,
        *,
        host: str = "127.0.0.1",
        port: int = 9000,
        protocol_version: str = "0.2.1",
    ):
        self.host = host
        self.port = port
        self.protocol_version = protocol_version
        # 默认用全局 agent_list；可传子集
        self.agent_list = agent_list if agent_list is not None else None
        self._base_url = f"http://{host}:{port}"

    def _get_agent_list(self) -> dict[str, Any]:
        if self.agent_list is not None:
            return self.agent_list
        from tangyuanAI.Agent_list import agent_list
        return agent_list

    # === Agent Card ===

    def agent_card(self, name: str) -> dict[str, Any]:
        """生成单个 agent 的 A2A Agent Card。"""
        agents = self._get_agent_list()
        agent = agents[name]
        description = getattr(agent, "description", "") or ""
        return {
            "name": name,
            "description": description,
            "url": f"{self._base_url}/a2a/v1",
            "version": "1.0",
            "capabilities": {"streaming": True, "pushNotifications": False},
            "skills": [],
            "protocolVersion": self.protocol_version,
        }

    def index_card(self) -> dict[str, Any]:
        """生成 A2A Agent Card（含所有 agent）。"""
        agents = self._get_agent_list()
        names = sorted(agents.keys())
        return {
            "name": "tangyuanAI-agents",
            "description": f"tangyuanAI 本地 agent 集群（{len(names)} 个）",
            "url": f"{self._base_url}/a2a/v1",
            "version": "1.0",
            "capabilities": {"streaming": True, "pushNotifications": False},
            "skills": [],
            "agents": [self.agent_card(n) for n in names],
            "protocolVersion": self.protocol_version,
        }

    # === JSON-RPC 处理 ===

    def _handle_json_rpc(self, request: dict[str, Any]) -> dict[str, Any]:
        """处理 A2A JSON-RPC 请求（同步 → 内部 asyncio.run）。"""
        from .a2a_protocol import (
            make_json_rpc_error,
            make_json_rpc_response,
            parse_json_rpc,
        )

        rpc_id = request.get("id")
        try:
            req = parse_json_rpc(request)
            method = req["method"]
            params = req.get("params") or {}

            if method in ("tasks/send", "tasks/sendSubscribe"):
                # 取 message text → 调 agent
                message = params.get("message") or {}
                parts = message.get("parts") or []
                text = "".join(
                    p.get("text", "") for p in parts if p.get("kind") == "text"
                )
                agent_name = params.get("agent") or self._single_agent_name()
                if not text.strip():
                    return make_json_rpc_error(-32602, "message 缺 text parts", rpc_id)

                result = self._call_agent(agent_name, text)
                return make_json_rpc_response(result, rpc_id)

            return make_json_rpc_error(-32601, f"未知 method: {method}", rpc_id)

        except ValueError as e:
            return make_json_rpc_error(-32600, str(e), rpc_id)
        except Exception as e:
            logger.error(f"A2A handler 异常: {e}")
            return make_json_rpc_error(-32603, f"内部错误: {e}", rpc_id)

    def _single_agent_name(self) -> str:
        """当 agent_list 只有 1 个 agent 时，自动选它（便于单 agent 部署）。"""
        agents = self._get_agent_list()
        if len(agents) == 1:
            return next(iter(agents))
        raise ValueError("多 agent 时 tasks/send 需要 params.agent 指定调用哪个")

    def _call_agent(self, agent_name: str, text: str) -> dict[str, Any]:
        """调本地 agent 的 conversation_with_tool，构造 A2A task result。"""

        agents = self._get_agent_list()
        if agent_name not in agents:
            raise KeyError(f"agent 不存在: {agent_name}")

        agent = agents[agent_name]
        reply = agent.conversation(text)

        import uuid as _uuid
        task_id = _uuid.uuid4().hex
        return {
            "id": task_id,
            "status": {"state": "completed"},
            "artifacts": [
                {"name": "reply", "parts": [{"kind": "text", "text": reply or ""}]}
            ],
        }

    # === HTTP handler（aiohttp） ===

    def app(self):
        """构造 aiohttp.web.Application（含路由）。"""
        try:
            from aiohttp import web
        except ImportError as e:
            raise ImportError(
                "A2AExporter 需要 aiohttp。Run `pip install tangyuanAI[a2a]`."
            ) from e

        app = web.Application()

        async def handle_agent_card(_request):
            return web.json_response(self.index_card())

        async def handle_tasks(request):
            # 注：这里走同步 _handle_json_rpc 是已知 trade-off —— agent 是同步 API。
            # 改 full async 需要 agent.conversation_with_tool 有 async 入口。
            try:
                body = await request.json()
            except Exception:
                from .a2a_protocol import make_json_rpc_error
                return web.json_response(
                    make_json_rpc_error(-32700, "无效 JSON"),
                    status=400,
                )
            response = self._handle_json_rpc(body)
            return web.json_response(response)

        async def handle_tasks_subscribe(request):
            """tasks/sendSubscribe —— SSE 流式。
            当前 agent.conversation_with_tool 是同步入口，所以用 chunked 单条 send 模拟流。
            """
            try:
                from aiohttp import web
            except ImportError:
                raise
            try:
                body = await request.json()
            except Exception:
                from .a2a_protocol import make_json_rpc_error
                return web.json_response(
                    make_json_rpc_error(-32700, "无效 JSON"),
                    status=400,
                )
            response = self._handle_json_rpc(body)
            resp = web.Response(
                content_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )
            # 单条 chunk 包成 SSE event 流出去
            import json as _json
            resp.body = _json.dumps(response).encode("utf-8")
            return resp

        app.router.add_get("/.well-known/agent.json", handle_agent_card)
        app.router.add_post("/a2a/v1/tasks/send", handle_tasks)
        app.router.add_post("/a2a/v1/tasks/sendSubscribe", handle_tasks_subscribe)
        return app

    async def serve(self) -> None:
        """阻塞启动 A2A HTTP server。"""
        from aiohttp import web

        app = self.app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info(f"A2A Exporter 启动: {self._base_url}")

        # 阻塞
        while True:
            await asyncio.sleep(3600)

    def serve_forever(self) -> None:
        """同步阻塞启动（内部 asyncio.run）。"""
        asyncio.run(self.serve())
