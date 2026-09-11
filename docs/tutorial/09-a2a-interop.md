---
slug: 09-a2a-interop
title: A2A 互操作
order: 9
icon: LAN_OUTLINED
---

# 09 A2A Interop

> 🎯 学完能把本地 agent 暴露成 A2A 远端协议,或把远端 A2A agent 导入本地。

## 概念

[A2A(Agent-to-Agent)](https://a2a.dev)是一个跨厂商 Agent 互操作协议(JSON-RPC 2.0 over HTTP)。

tangyuanAI **核心原生**支持:

- **导出**:`A2AExporter` 把本地 `agent_list` 暴露成 A2A server
- **导入**:`register_a2a_agent(url)` 把远端 A2A server 拉成本地 `A2AAgentProxy`,像本地 agent 一样调

## 5 行代码起步(导出)

```python
from tangyuanAI.a2a_exporter import A2AExporter

agents = {
    "writer": tangyuanAI.agent_list["writer"],
    "researcher": tangyuanAI.agent_list["researcher"],
}
exporter = A2AExporter(agent_list=agents, port=9000)
await exporter.serve()      # ← 阻塞;或 serve_forever() 启后台
```

## 5 行代码起步(导入)

```python
import tangyuanAI

proxy = tangyuanAI.register_a2a_agent("http://other-server:9000")
# proxy 是 A2AAgentProxy,有 name / description / conversation(...) 等
tangyuanAI.agent_list[proxy.name]   # 注册到本地,其他 agent 可 ask_for_help
```

## 完整 demo

- [`docs/a2a.md`](../a2a.md) —— 协议 / 客户端 / 导出 / source tracking 全细节

## 进阶

- 部署到 Cloudflare / 服务器:详见 [`docs/a2a.md`](../a2a.md#部署)
- A2A Agent Card:`/.well-known/agent.json` 由 exporter 自动生成

## 常见问题

**Q: 远端 A2A agent 的工具列表我看不到,怎么知道能调什么?**
A: `GET /.well-known/agent.json` 暴露 Agent Card,含 `name` / `description` / `skills`。A2AAgentProxy 注册时自动 fetch。

**Q: 本地 agent 怎么调远端 agent 的工具?**
A: 走 `ask_for_help(proxy.name, "...")`,A2A 协议细节全在 proxy 里封装。