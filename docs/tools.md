---
slug: tools
title: 工具
order: 4
icon: BUILD_OUTLINED
---

# 工具

> 工具注册：`@tool_registry.register_tool`（传统 JSON Schema）vs `@builtin_tool`（从签名自动推导 schema）。

## 两种写法对比

| 维度 | `register_tool` | `builtin_tool` |
|---|---|---|
| schema 来源 | 手写 `parameters={...}` | 自动从签名 + 类型注解推导 |
| 适用场景 | 模块级工具（独立函数） | Agent 内置方法（`self.xxx`） |
| 参数校验 | 运行时不做 | 可选 Pydantic `params_model` |
| ACL | `allowed_agents=[...]` | 通过 `tool_registry` 同款 |

## 写法 1：`@tool_registry.register_tool`（模块级函数）

```python
import tangyuanAI

@tangyuanAI.tool_registry.register_tool(
    allowed_agents=["my_agent"],
    name="add",
    description="求两数之和",
    parameters={
        "type": "object",
        "properties": {
            "a": {"type": "number"},
            "b": {"type": "number"},
        },
        "required": ["a", "b"],
    },
)
def add(a: float, b: float) -> float:
    return a + b
```

## 写法 2：`@builtin_tool`（Agent 内置方法）

```python
from tangyuanAI import builtin_tool

class MyAgent(tangyuanAI.Agent):
    protocol = "openai"  # 或 "anthropic" / "openai-responses"
    @builtin_tool(
        description="求两数之和",
        params={"a": "第一个加数", "b": "第二个加数"},
    )
    def add(self, a: float, b: float) -> float:
        return a + b
```

schema 自动从签名 + 类型注解推导，无需手写 JSON Schema。

> 子类覆盖 `@builtin_tool` 装饰的父类方法时，`__init_subclass__` 钩子会把父类的 meta 复制到子类方法，schema 不丢。

## ACL 注意事项

`allowed_agents` 必须传 agent **name**（不是 uuid）：

```python
@tangyuanAI.tool_registry.register_tool(
    allowed_agents=["my_agent"],   # ✓ name
    # allowed_agents=["my-uuid"], # ✗ uuid —— check_permission 内部会先做 uuid→name 翻译
    #                            #    再去跟 name 列表比对，必然失败
    name="add",
    description="...",
    parameters={...},
)
def add(...): ...
```

`tool_registry.check_permission(uuid, name)` 实际逻辑：

```python
# uuid -> name 翻译
if agent_name in self._uuid_to_name:
    agent_name = self._uuid_to_name[agent_name]
# 拿 tool 的 allowed_agents 列表（元素是 name）比对
return agent_name in tool_info["allowed_agents"]
```

## Pydantic 参数校验

`@builtin_tool` 方法可以声明 `params_model`，框架在调用前用 Pydantic 校验 LLM 的入参：

```python
from pydantic import BaseModel, Field

class AddParams(BaseModel):
    a: float = Field(..., description="第一个加数")
    b: float = Field(..., description="第二个加数")

class MyAgent(tangyuanAI.Agent):
    protocol = "openai"
    @builtin_tool(
        description="求两数之和",
        params_model=AddParams,  # 显式传
    )
    def add(self, a: float, b: float) -> float:
        return a + b
```

校验失败时把错误信息回给 LLM 让它重试。

## 工具调用与执行

| 行为 | 实现 |
|---|---|
| 单次执行 | `_tool_runner.submit(tool_func, ..., timeout=self.tool_timeout)` |
| 超时（> `tool_timeout` 秒） | 转后台 future，返回 `(None, task_id)`，让 LLM 继续做别的 |
| 钩子 | `register_tool_hook(event_type, ...)`，`event_type` ∈ `{before, after, error}` |
| 工具返回值 | 字符串或可 JSON 序列化的对象 |

```python
class MyAgent(tangyuanAI.Agent):
    protocol = "openai"
    def __init__(self):
        super().__init__()
        self.register_tool_hook(self._audit)

    def _audit(self, event_type, tool_name, tool_args, tool_result, task_id):
        if event_type == "error":
            logger.error(f"工具 {tool_name} 失败：{tool_result}")
```

详见 [output-and-hooks.md](output-and-hooks.md)。