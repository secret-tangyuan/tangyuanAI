---
slug: 03-tools
title: 工具
order: 3
icon: BUILD_OUTLINED
---

# 03 Tools

> 🎯 学完能给 agent 装自定义工具,并配置 ACL / FC 模式 / 工具校验。

## 概念

Agent 调用工具分两种模式:

| 模式 | 触发方式 | 适用 |
| --- | --- | --- |
| **FC(Function Calling)** | `fc_model=True` 时,LLM 返回结构化 `tool_calls` | 现代 LLM,推荐 |
| **XML 标签** | `fc_model=False` 时,LLM 在文本里输出 `<tool_name>...</tool_name>` | 老的非 FC 模型,XML 协议兜底 |

工具注册统一用 `@tool_registry.register_tool`(外部工具)或 `@builtin_tool`(内置类方法工具)。两者都自动接 ACL、Pydantic 校验、超时。

## 5 行代码起步

```python
@tangyuanAI.tool_registry.register_tool(
    description="查询某城市天气",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
    allowed_agents=["weather"],       # ← ACL,只允许 weather agent 调
)
def get_weather(city: str) -> str:
    return f"{city}今天晴,温度 25°C"

class WeatherAgent(tangyuanAI.Agent):
    protocol = "openai"
    fc_model = True                  # ← 走 FC 模式
    prompt = "用 get_weather 工具回答"
    # ...
```

## 完整 demo

- [`examples/example2_custom_tools.py`](examples/example2_custom_tools.py) —— FC + 多工具 + Pydantic 校验

## 进阶

- [`docs/tools.md`](../tools.md) —— 注册细节 / Pydantic 自动校验
- [`docs/builtin-tools.md`](../builtin-tools.md) —— 8 个内建工具一览(`ask_for_help` / `attempt_completion` 等)

## 常见问题

**Q: 怎么限制某个 agent 只能用部分工具?**
A: `allowed_agents=["weather", "researcher"]`,ACL 在 `_dispatch_tool` 里强制检查。

**Q: 工具里能调用别的工具吗?**
A: 可以,但不要直接 import 注册的 tool——会绕过 ACL。用 `agent_list[other_agent].ask_for_help(...)` 跨 agent 调。

**Q: Pydantic 校验失败怎么报错?**
A: 工具装饰器里设 `params_model: type[BaseModel]`,框架会自动校验。校验失败会写到 history 里,LLM 看得到结构化错误。