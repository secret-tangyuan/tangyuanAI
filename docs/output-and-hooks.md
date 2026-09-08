---
slug: output-and-hooks
title: 输出与钩子
order: 7
icon: EXTENSION_OUTLINED
---

# 输出与钩子

> `pack` / `out` 输出事件总线（v0.3.1+ 双协议对齐）；`register_tool_hook` 工具调用钩子。

## 输出事件总线：`pack` → `out`

### 设计意图

`pack` 是"事件打包"层：把"AI 输出一段文本"、"调用某个工具"、"工具返回结果"等原始事件封装成带 `ai_uuid` / `ai_name` / `task_id` / `timestamp` 的 content dict，再交给 `out(content)`。

- 想**接管输出行为**（流式 / UI / 自定义 logger / 静默等）→ 覆写 `out`
- **不要**覆写 `pack`（`out` 才是 canonical 钩子）
- 框架在子类覆写 `pack` 但未覆写 `out` 时会在构造时给出一条 warning

### `pack` 签名

```python
def pack(
    self,
    message: Optional[str] = None,
    tool_model: bool = False,
    tool_name: Optional[str] = None,
    tool_parameter: Optional[dict] = None,
    finish_task: bool = False,
    other: bool = False,
    tool_result: Any = None,
) -> None: ...
```

四种 content dict（按优先级匹配第一个 True 的分支）：

| 触发条件 | content |
|---|---|
| `finish_task=True` | `{"task": True, "task_id": ..., "timestamp": ..., "ai_uuid": ..., "ai_name": ...}` |
| `tool_model=True` | `{"tool_name": ..., "tool_parameter": ..., ..., "task": False}` |
| `tool_result is not None` | `{"tool_result": ..., "tool_name": ..., ..., "task": False}` |
| 其他 | `{"message": ..., "ai_uuid": ..., "ai_name": ..., "other": ..., "task": False}` |

### 默认 `out`（Agent 工厂基类，所有协议一致）

```python
def out(self, content: dict) -> None:
    if content.get("tool_result") is not None:
        print(f"\n[工具结果] {content.get('tool_name', '')} → {content.get('tool_result')}")
        return
    if content.get("tool_name"):
        print(f"\n[工具] {content.get('tool_name')} 参数={content.get('tool_parameter')}")
        return
    if content.get("task"):
        print(f"\n[完成] {content.get('message', '')}")
        return
    if content.get("message") is not None:
        print(content.get("message"), end="")
```

> `Agent + protocol` 任意协议都走这份默认 `out`；想劫持输出就重写 `out`（推荐），
> 不要覆写 `pack`。

### 自定义输出（流式 UI / 静默 / JSON 日志）

```python
import json

class MyAgent(tangyuanAI.Agent):                     # 推荐写法：Agent + protocol
    protocol = "openai"                             # 一行切协议
    def out(self, content: dict) -> None:
        # 推到前端 WebSocket
        if hasattr(self, "_ws"):
            self._ws.send(json.dumps(content, ensure_ascii=False))
        # 同时写本地日志
        with open("agent.log", "a") as f:
            f.write(json.dumps(content, ensure_ascii=False) + "\n")
```

## 工具调用钩子

```python
class MyAgent(tangyuanAI.Agent):
    protocol = "openai"
    def __init__(self):
        super().__init__()
        self.register_tool_hook(self._audit)

    def _audit(self, event_type, tool_name, tool_args, tool_result, task_id):
        # event_type: 'before' | 'after' | 'error'
        if event_type == "before":
            logger.info(f"[{task_id}] 调用 {tool_name}({tool_args})")
        elif event_type == "after":
            logger.info(f"[{task_id}] {tool_name} -> {tool_result}")
        elif event_type == "error":
            logger.error(f"[{task_id}] {tool_name} 失败：{tool_result}")
```

钩子在所有协议（`protocol = "openai" | "anthropic" | "openai-responses"`）的同步+异步两条对话路径都生效（`conversation` / `aconversation`）。

## 关键修复历史

| 版本 | 修复 |
|---|---|
| v0.3.0 | `AnthropicAgent.conversation(stream=False)` 丢字（text 只入 `full_text` 不进 `assistant_blocks`） |
| v0.3.0 | `BaseAgent.conversation` 同步多轮吞掉 LLM 最终回复（`if tool: return work_history[-1]` 错把 tool_result 当答案） |
| v0.3.1 | 上面两个 bug 都修了；`AnthropicAgent` 内部 `self.out({...})` 全部切到 `self.pack(...)` |
| v1.1.1-rc1 | `Agent.out` 优先打印 `tool_result`（之前会被 `tool_name` 分支吞掉） |