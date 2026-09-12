# tangyuanAI

> 一个轻量的多 LLM 协议 Agent 框架,把 provider 方言差异收拢到一处。
>
> A lightweight multi-LLM-protocol Agent framework that puts provider dialect differences in one place.

[![PyPI](https://img.shields.io/pypi/v/tangyuanAI.svg)](https://pypi.org/project/tangyuanAI/)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI](https://github.com/secret-tangyuan/tangyuanAI/actions/workflows/python-package.yml/badge.svg)](https://github.com/secret-tangyuan/tangyuanAI/actions)

[文档站 / Docs](https://ai.secret-tangyuan.com/docs) ·
[学习路径 / Tutorial](./TUTORIAL.md) ·
[CHANGELOG](./CHANGELOG.md)

---

## 1 分钟讲清楚 / 60-second pitch

每家 LLM 都有自己的协议方言(OpenAI Chat Completions / Anthropic Messages / OpenAI Responses / 你公司机房网关)。**tangyuanAI 写一份 Agent 代码就能切任意 provider**——切协议是改一行类字段,不是重写循环。

Every LLM has its own wire format. **Write your Agent once; switch providers with a single class field** instead of rewriting your loop.

---

## 30 秒 demo

```bash
# 推荐 uv(本仓库 CI / docs-site 都用 uv)
uv pip install tangyuanAI
# 或 pip install tangyuanAI

export API_KEY="sk-..."                    # OpenAI 协议
export ANTHROPIC_API_KEY="sk-ant-..."      # Anthropic 协议(可选)
```

```python
import os, tangyuanAI
from tangyuanAI import template_agent
from tangyuanAI.Agent_list import activate_template

@tangyuanAI.tool_registry.register_tool(
    description="查询某城市天气",
    parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)
def get_weather(city: str) -> str:
    return f"{city}今天晴，25°C"

@template_agent("weather", uuid="weather-1", description="天气助手")
class WeatherAgent(tangyuanAI.Agent):                # ← 协议无关工厂基类
    protocol     = "openai"                            # ← 一行切协议
    prompt       = "你是天气助手,用 get_weather 工具回答"
    api_provider = os.getenv("API_BASE", "https://api.openai.com/v1")
    model_name   = os.getenv("MODEL", "gpt-5")
    api_key      = os.getenv("API_KEY")

activate_template("weather")
print(tangyuanAI.agent_list["weather"].conversation("北京今天天气怎么样？"))
```

切协议只改一个字段:

```python
class ReviewerAgent(tangyuanAI.Agent):
    protocol     = "anthropic"                          # ← 改这一行
    api_provider = "https://api.anthropic.com"
    model_name   = "claude-3-5-sonnet-latest"
    api_key      = os.getenv("ANTHROPIC_API_KEY")
```

---

## 怎么写好 Agent —— 4 件事 / How to write good Agents

1. **`@template_agent` 注册,`activate_template` 实例化。** 装饰器只登记;激活才实例化——import 时不付成本,真用时再实例化。
2. **`description=` 是一句话不是段。** 它是别的 Agent 决定"要不要调我"时读的。
3. **工具描述决定工具选择。** schema / docstring 直接决定 LLM 调 `get_user_orders(user_id=...)` 还是 `list_all_orders()`。
4. **自定义 `out()` 是接入点。** 默认 print;覆写可推到 logger / queue / UI。**别动 `pack()`**。

---

## 完整内容去哪看 / Where to read more

| 想了解 | 看哪 |
| --- | --- |
| 从零开始 30 分钟跑通第一个 | **[TUTORIAL.md](./TUTORIAL.md)** |
| 完整 API / 钩子 / ACL / MCP / 持久化 / Skill | **[文档站](https://ai.secret-tangyuan.com/docs)** |
| 协议背景 + A2A 对比 + 架构图 | [docs/concepts.md](./docs/concepts.md) *(本批未写,见 issues)* |
| 版本变更 | [CHANGELOG.md](./CHANGELOG.md) |
| 协议简单性 demo | [examples/](./examples/) |

---

## 开发与测试

```bash
git clone https://github.com/secret-tangyuan/tangyuanAI.git
cd tangyuanAI
uv sync --group dev
uv run pytest -v
uv run ruff check .
```

`tests/_llm_mock.py` 提供了完整 wire-format mock,跑测试不用 API key。

加新 transport?实现 `LLMTransport` 并在 `__init__.py` 调 `register_protocol(name, cls)`。

---

## 许可证 / License

Apache License 2.0 · Copyright 2025-2026 [Secret Tangyuan](https://github.com/secret-tangyuan)

完整许可证见 [LICENSE](./LICENSE)。
