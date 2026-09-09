---
slug: protocols
title: 通信协议
order: 6
icon: SWAP_HORIZ_OUTLINED
---

# 协议

> OpenAI 兼容 Chat Completions vs Anthropic Messages API；通过 `Agent` 工厂基类 + `protocol` 字段统一选择。

## 两种协议对比

| 维度 | OpenAI | Anthropic |
|---|---|---|
| Endpoint | `/v1/chat/completions` | `/v1/messages` |
| System prompt | messages[0] | 顶层 `system` 字段 |
| 工具 schema | `{type: function, function: {name, description, parameters}}` | `{name, description, input_schema}` |
| 工具调用 | `tool_calls[].function.{name, arguments}` | `content: [{type: tool_use, id, name, input}]` |
| 工具结果 | `role: tool, tool_call_id, content` | `role: user, content: [{type: tool_result, tool_use_id, content}]` |
| 流式事件 | `chunk.choices[].delta.content` | `message_start` / `content_block_*` / `message_delta` / `message_stop` |
| 鉴权头 | `Authorization: Bearer <key>` | `x-api-key: <key>` + `anthropic-version` |

> `protocol` 字段值 `openai` / `anthropic` / `openai-responses` 决定实际基类；
> 旧写法直接继承 `BaseAgent` / `AnthropicAgent` 仍兼容（v0.4.2+），但**已 deprecated**（v1.3.0 删除）。

## `Agent` 工厂基类（v0.2.2+）—— 推荐写法

继承 `Agent` + `protocol` 字段切协议；不要直接 `BaseAgent` / `AnthropicAgent`：

```python
import tangyuanAI

@tangyuanAI.template_agent("chat", uuid="chat-uuid", description="chat agent")
class ChatAgent(tangyuanAI.Agent):
    protocol = "openai"  # 或 "anthropic" / "openai-responses"
    prompt = "..."
    model_name = "..."
    api_key = "..."
    api_provider = "..."  # 对应协议的 base URL
```

`_ProtocolMeta` metaclass 在类创建时根据 `protocol` 字段把 `Agent` 占位基类替换成 `_OpenAIBase` / `_AnthropicBase` / `_OpenAIResponsesBase` 中相应的一个，运行时零开销。

## 双协议公开 API 对称性（v0.3.1）

无论 `protocol` 取哪个值，Agent 类的方法集合完全一致：

| 方法 | 说明 |
|---|---|
| `__init__(new_load=True)` | 初始化 |
| `conversation(messages, *, tooluse=True, addhistory=True, images=None)` | 同步对话（v1.3.0+；旧名 `conversation_with_tool` 已 deprecated alias） |
| `aconversation(messages, *, tooluse=True, addhistory=True, images=None)` | 异步对话（旧名 `aconversation_with_tool` 已 deprecated alias） |
| `out(content: dict) -> None` | 输出回调（可重写） |
| `pack(message, tool_model, tool_name, tool_parameter, finish_task, other, tool_result)` | 事件打包（推荐重写 `out` 而不是 `pack`） |
| `register_tool_hook(hook_func)` | 注册工具钩子 |
| `ask_for_help(agent_id, message)` | 内置工具：跨 Agent 协作 |
| `list_agents()` | 内置工具：列出已注册 Agent |
| `attempt_completion(report_content)` | 内置工具：标记完成 |
| `reload()` | 内置工具：重载 system prompt |
| `register_template / activate_template / deactivate_template / list_templates` | 模板池管理（4 个 builtin_tool） |
| `get_all_available_tools()` | 列出当前可用工具 |

## 自定义 Anthropic 端点

`api_provider` **没有默认值**（v0.2.2+ 起强制显式设置），避免"忘记设置 endpoint 误走到官方 API"的隐性 bug。可指向任意兼容 Anthropic Messages API 的服务：

```python
class MyAgent(tangyuanAI.Agent):
    protocol = "anthropic"                               # ← 一行切 Anthropic 协议
    api_provider = "https://api.anthropic.com"          # 官方
    # api_provider = "https://your-proxy.example.com"   # 第三方代理
    # api_provider = "https://your-proxy.com/v1/messages" # 完整 endpoint
    # api_provider = "bedrock-runtime.us-east-1.amazonaws.com"  # AWS Bedrock
```

`_endpoint()` 智能拼接：

- 末尾是 `/v1/messages` → 原样使用
- 末尾是 `/v1` → 拼上 `/messages`
- 其他 → 拼上 `/v1/messages`

如果网关要求额外 header（`Authorization: Bearer xxx` / 租户 ID），在子类 `__init__` 里覆盖 `self.headers`：

```python
def __init__(self, new_load=True):
    super().__init__(new_load=new_load)
    self.headers["X-Tenant-Id"] = "tenant-001"
    # self.headers["Authorization"] = f"Bearer {self.api_key}"
    # self.headers.pop("x-api-key", None)
```

完整示例见 `examples/example6_anthropic_custom_provider.py`。