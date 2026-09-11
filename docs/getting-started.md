---
slug: getting-started
title: 快速开始
order: 2
icon: ROCKET_LAUNCH_OUTLINED
---

# 快速开始

> 5 分钟跑通第一个 Agent。

## 安装

作者推荐用 [uv](https://docs.astral.sh/uv/) 管理依赖(也支持锁文件 + 虚拟环境):

```bash
# 方式 1: uv (推荐, 快 + 锁文件)
uv pip install tangyuanAI        # 装到当前 venv
# 或建独立 venv:
uv venv && source .venv/bin/activate && uv pip install tangyuanAI

# 方式 2: pip (传统)
pip install tangyuanAI
```

需要 Python 3.10+。无额外可选依赖。

> 项目内 CI / 文档站构建也都用 uv(`uv run pytest` / `uv run uvicorn`)。

## 准备 API Key

```bash
export API_KEY="sk-..."               # OpenAI 协议
export ANTHROPIC_API_KEY="sk-ant-..." # Anthropic 协议
```

> v0.2.2+ 起 `api_key` 走 `os.getenv()` 读取，**不要硬编码**到子类里。

## 第一个 Agent（OpenAI 协议）

```python
import os
import tangyuanAI

# 注册一个工具
@tangyuanAI.tool_registry.register_tool(
    allowed_agents=["weather"],
    name="get_weather",
    description="查询某城市当前天气",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string", "description": "城市名"}},
        "required": ["city"],
    },
)
def get_weather(city: str) -> str:
    return f"{city}今天晴，25°C"

# 注册 Agent（v0.3.0+ 模板池写法）
from tangyuanAI import template_agent
from tangyuanAI.Agent_list import activate_template

@template_agent("weather", uuid="weather-uuid", description="天气小助手")
class WeatherAgent(tangyuanAI.Agent):                     # ← 推荐：协议无关工厂基类
    protocol = "openai"                                  # ← 一行切 OpenAI 协议
    prompt = "你是天气助手，使用 get_weather 工具查询天气。"
    api_provider = "https://api.example.com/v1/chat/completions"
    model_name = os.getenv("OPENAI_MODEL")
    api_key = os.getenv("API_KEY")

# 激活模板（也可由 LLM 在对话中通过 activate_template builtin_tool 触发）
activate_template("weather")

# 跑一次对话
agent = tangyuanAI.agent_list["weather"]
print(agent.conversation("北京今天天气怎么样？"))
```

## 第一个 Agent（Anthropic 协议）

```python
import os
import tangyuanAI
from tangyuanAI import template_agent
from tangyuanAI.Agent_list import activate_template

@template_agent("reviewer", uuid="reviewer-uuid", description="评审 Agent")
class ReviewerAgent(tangyuanAI.Agent):                  # ← 同一基类，切协议即可
    protocol = "anthropic"                              # ← 一行切 Anthropic 协议
    prompt = "你是评审助手。完成工作后用 attempt_completion 汇报。"
    api_provider = "https://api.anthropic.com"
    model_name = os.getenv("ANTHROPIC_MODEL")
    api_key = os.getenv("ANTHROPIC_API_KEY")

activate_template("reviewer")
agent = tangyuanAI.agent_list["reviewer"]
print(agent.conversation("请评审：xxx"))
```

> 同一份 `agent_list`，OpenAI Agent 和 Anthropic Agent 可以直接 `ask_for_help` 互调。

## 下一步

- [agent-registration.md](agent-registration.md) — 模板池 vs `@register_agent`（旧写法已弃用）
- [tools.md](tools.md) — 工具注册的两种写法
- [protocols.md](protocols.md) — 双协议统一：`Agent` 工厂基类 + `protocol` 字段