---
slug: a2a
title: A2A 互操作（Agent-to-Agent 协议）
order: 10
icon: LAN_OUTLINED
---

# A2A 互操作（Agent-to-Agent 协议）

> **v1.0.0+**。tangyuanAI 支持 Google A2A 协议：本地 agent 可被发现、可被远端调用；也可发现并调用远端 A2A agent。

> **A2A 为核心原生支持（v1.1.0+ 起不随插件迁移）**。导出需要 aiohttp：`pip install "tangyuanAI[a2a]"`；未装 aiohttp 时导出相关 API 给出清晰报错。

## 什么是 A2A

[Google A2A 协议](https://a2a-protocol.org)（Agent-to-Agent）是 agent 间互操作的标准：
- **Agent Card**：`/.well-known/agent.json` 描述 agent 能力（name / description / skills / endpoint）
- **JSON-RPC 2.0**：`tasks/send`（调用）、`tasks/sendSubscribe`（流式）
- 跨进程 / 跨机器发现 + 调用

## 导入：调用远端 A2A agent

**场景**：另一个团队用 A2A 暴露了一个 agent（`http://remote:9000`），你想让本地 agent 调它。

```python
import tangyuanAI as t

# 1. 发现 + 注册远端 agent 到本地 agent_list（source 标记为 a2a:<url>）
proxy = t.register_a2a_agent("http://remote:9000")
# → A2AAgentProxy(name='a2a_xxx', url='http://remote:9000')
# → 已注册到 agent_list['a2a_xxx']，source='a2a:http://remote:9000'

# 2. 本地 agent 通过 ask_for_help 透明调用远端
result = t.agent_list["scheduling_agent"].ask_for_help(
    agent_id="a2a_xxx",   # 远端 agent 的本地代理名
    message="帮我查一下天气",
)

# 3. 或直接调 proxy
reply = proxy.conversation("帮我查一下天气")
```

### 来源跟踪

区分"框架内 agent"与"从 A2A 导入的远端 agent"：

```python
t.agent_source("a2a_xxx")          # → "a2a:http://remote:9000"
t.agent_source("local_agent")       # → "internal"
t.list_internal_agents()            # → 框架内定义的 agent 名
t.list_external_agents()            # → A2A 导入的 agent 名
t.list_agents_with_source()         # → [(name, source), ...]
```

## 导出：把本地 agent 暴露为 A2A

**场景**：你想让别的系统发现并调用你的本地 agent。

```bash
pip install "tangyuanAI[a2a]"   # 需要 aiohttp
```

```python
import tangyuanAI as t
from tangyuanAI.a2a_exporter import A2AExporter

# 默认暴露全部 agent_list；可传子集 {"writer": writer_agent}
exporter = A2AExporter(host="127.0.0.1", port=9000)
await exporter.serve()   # 阻塞；或用 exporter.serve_forever()
```

### 外部发现

```bash
# Agent Card（含所有 agent）
curl http://127.0.0.1:9000/.well-known/agent.json

# 调用（多 agent 时用 params.agent 指定）
curl -X POST http://127.0.0.1:9000/a2a/v1/tasks/send \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tasks/send",
       "params":{"id":"t1","agent":"writer",
                 "message":{"role":"user",
                            "parts":[{"kind":"text","text":"写个标题"}]}}}'
```

响应：
```json
{
  "jsonrpc": "2.0", "id": "1",
  "result": {
    "id": "t1",
    "status": {"state": "completed"},
    "artifacts": [{"name": "reply", "parts": [{"kind": "text", "text": "写好了: 写个标题"}]}]
  }
}
```

## 协议模块

- `tangyuanAI/a2a_protocol.py`：JSON-RPC 2.0 构造/解析 + Agent Card + 文本提取（纯数据结构，无网络依赖）
- `tangyuanAI/a2a_client.py`：发现 + 调用 + 注册（httpx）
- `tangyuanAI/a2a_exporter.py`：aiohttp HTTP server（optional `[a2a]`）

## 与 ask_for_help 的关系

本地 agent 用 `ask_for_help` 调任何 agent_list 里的 agent——包括 A2A 导入的代理。
`A2AAgentProxy` 长得像普通 agent（有 name / description / conversation），
底层把消息转发到远端 A2A 端点。对调度 agent 来说，本地 / 远端是透明的。