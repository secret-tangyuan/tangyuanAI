# 02 Protocols and Agents

> 🎯 学完能用同一个 Agent 类切到 OpenAI / Anthropic / OpenAI Responses 三种 provider,以及接公司网关。

## 概念

`Agent` 是协议无关的工厂基类——它通过 `protocol` 字段(类属性)选择实际的协议实现。框架内部用 metaclass (`_ProtocolMeta`) 在类创建时把 `Agent` 占位基类替换成对应协议的真正基类。

切 provider = 改一个类字段。**零代码改动**。

| Protocol | Wire format | 默认 endpoint |
| --- | --- | --- |
| `"openai"` | `/v1/chat/completions` | `https://api.openai.com/v1` |
| `"anthropic"` | `/v1/messages` | `https://api.anthropic.com` |
| `"openai-responses"` | `/v1/responses` | `https://api.openai.com/v1` |

## 5 行代码起步

```python
@tangyuanAI.template_agent("writer", uuid="writer-1", description="...")
class Writer(tangyuanAI.Agent):
    protocol = "anthropic"     # ← 改这一行就从 openai 切到 anthropic
    prompt = "你是写作助手"
    api_provider = "https://api.anthropic.com"
    model_name = "claude-3-5-sonnet-latest"
    api_key = os.getenv("ANTHROPIC_API_KEY")
```

切到 OpenAI Responses(新版 API,内置 web search)只改一个值:

```python
protocol = "openai-responses"   # ← 改这一行
model_name = "gpt-5-responses"
```

## 接公司网关

```python
class MyGatewayAgent(tangyuanAI.Agent):
    protocol = "openai"          # gateway 通常讲 OpenAI 兼容协议
    api_provider = "https://internal-gateway.company.com/v1"
    # model_name / api_key 按 gateway 要求填
```

## 完整 demo

- [`examples/example1_basic.py`](examples/example1_basic.py)
- [`examples/example2_custom_tools.py`](examples/example2_custom_tools.py)—— 多协议对比

## 进阶

- [`docs/protocols.md`](../protocols.md) —— 协议差异 / 双协议对称性细节
- [`docs/agent-registration.md`](../agent-registration.md) —— `template_agent` vs `@register_agent` 的选择

## 常见问题

**Q: 我想接一个讲自定义协议的 LLM(比如 vLLM 自部署)?**
A: 实现一个 `LLMTransport` 子类 + `register_protocol("vllm", MyBase)`。详见 [`docs/protocols.md`](../protocols.md#自定义协议)。

**Q: `BaseAgent` / `AnthropicAgent` 直继承还能用吗?**
A: 兼容,但已 deprecated(v1.3.0 删)。新代码请用 `Agent + protocol`。