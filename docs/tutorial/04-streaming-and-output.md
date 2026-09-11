---
slug: 04-streaming-and-output
title: 流式输出与钩子
order: 4
icon: STREAM_OUTLINED
---

# 04 Streaming and Output

> 🎯 学完能让前端实时看到 agent 输出 / 工具调用进度。

## 概念

tangyuanAI 用两个钩子把"agent 输出"和"框架内部事件"分离开:

- **`pack(...)`** —— 把事件打包成结构化 dict(默认实现会 print)
- **`out(content: dict)`** —— 实际输出回调(默认 print,生产建议重写)

事件类型:`message` / `tool_name` / `tool_result` / `tool_model` / `finish_task` / `other` / `task`。

流式模式(`stream=True`)下 `chat_stream` / `achat_stream` 边收边 `pack`,所以 UI 可以实时刷新。

## 5 行代码起步

```python
class CLI(tangyuanAI.Agent):
    protocol = "openai"
    stream = True                                  # ← 开流式

    def out(self, content):                        # ← 重写输出回调
        kind = content.get("tool_name") or "msg"
        print(f"[{kind}] {content}", flush=True)
```

## 异步流式(前端用)

```python
class StreamAgent(tangyuanAI.Agent):
    protocol = "openai"
    stream = True

    async def on_text_chunk(self, chunk: str):
        await send_to_websocket(chunk)             # ← 每个 chunk 推前端
```

## 完整 demo

- [`examples/example5_custom_output.py`](examples/example5_custom_output.py) —— 重写 `out()` 把输出写到文件 / WebSocket

## 进阶

- [`docs/output-and-hooks.md`](../output-and-hooks.md) —— 所有事件类型 + 钩子(`before` / `after` / `error`)
- [`docs/protocols.md`](../protocols.md) —— 流式 wire format 细节

## 常见问题

**Q: 流式和非流式怎么选?**
A: 用户能看到实时的场景(聊天 UI)→ `stream=True`。批处理 / 后台 → `stream=False`,省一些反复 chunktime。

**Q: 工具调用时也有 stream 事件吗?**
A: 有。LLM 决定调工具的瞬间会 emit `tool_name` / `tool_parameter` 事件,工具执行完 emit `tool_result`。前端可以拿来做进度条。