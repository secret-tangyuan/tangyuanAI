---
slug: 01-getting-started
title: 快速开始
order: 1
icon: ROCKET_LAUNCH_OUTLINED
---

# 01 Getting Started

> 🎯 学完能跑通第一个 agent 并发起一次对话。

## 概念

tangyuanAI 把每个 LLM provider(OpenAI / Anthropic / OpenAI Responses)的协议差异收拢到一个**Transport**层。你只需要写一个 `Agent` 子类,设 `protocol = "..."`,框架就会自动用正确的 wire format 跟那个 LLM 对话。

Agent 类是协议无关的——同一个类设不同的 `protocol` 字段就走不同的 provider。

## 5 行代码起步

```python
import os, tangyuanAI
from tangyuanAI.Agent_list import activate_template

@tangyuanAI.template_agent("weather", uuid="weather-1", description="天气助手")
class WeatherAgent(tangyuanAI.Agent):
    protocol = "openai"                                # ← 改这一行切协议
    prompt = "你是天气助手"
    api_provider = "https://api.openai.com/v1"
    model_name = "gpt-5"
    api_key = os.getenv("API_KEY")

activate_template("weather")
print(tangyuanAI.agent_list["weather"].conversation("北京今天天气怎么样？"))
```

## 安装与运行

```bash
pip install tangyuanAI
export API_KEY="sk-..."
python my_agent.py
```

## 完整 demo

- [`examples/example1_basic.py`](examples/example1_basic.py) —— 完整 weather agent,含工具注册
- [`examples/example2_custom_tools.py`](examples/example2_custom_tools.py) —— 加自定义工具

## 进阶

- [02 protocols-and-agents](02-protocols-and-agents.md) —— 怎么切到 Anthropic / Responses
- [`docs/getting-started.md`](docs/getting-started.md) —— 完整安装与配置

## 常见问题

**Q: 跑出 `AuthenticationError` 怎么办?**
A: 检查 `API_KEY` 环境变量(或对应 provider 的 key,如 `ANTHROPIC_API_KEY`)。每个 provider 用自己的环境变量名。

**Q: `protocol` 字段支持哪些值?**
A: 内置 `openai` / `anthropic` / `openai-responses`。可用 `register_protocol("name", BaseClass)` 注册自定义(如 `tangyuanai register custom --module my.module`)。

**Q: 同步 vs 异步?**
A: 默认同步 `conversation()`,异步用 `await agent.aconversation()`。两者行为对称。