---
slug: agent-registration
title: Agent 注册
order: 3
icon: EDIT_NOTE_OUTLINED
---

# Agent 注册

> 两种写法：v0.3.0+ 模板池（推荐）vs `@register_agent`（已弃用但兼容）。

## 模板池写法（v0.3.0+ 推荐）

模板池把"声明"和"激活"分开：装饰器只把类登记到 `agent_template_pool`，**不实例化、不写入 `agent_list`**；实例化时机由 `activate_template(name)` 显式控制。

### 装饰器式

```python
import os
import tangyuanAI
from tangyuanAI import template_agent
from tangyuanAI.Agent_list import activate_template

@template_agent("my_agent", uuid="my-uuid", description="一句话说明用途")
class MyAgent(tangyuanAI.Agent):                                # ← 推荐：协议无关工厂基类
    protocol = "openai"                                          # ← 一行切协议
    prompt = "..."
    api_provider = "https://api.example.com/v1/chat/completions"
    model_name = os.getenv("OPENAI_MODEL")
    api_key = os.getenv("API_KEY")

# 显式激活
activate_template("my_agent")
agent = tangyuanAI.agent_list["my_agent"]
```

### 函数式

```python
from tangyuanAI.Agent_list import register_template, activate_template

class MyAgent(tangyuanAI.Agent):
    protocol = "openai"
    prompt = "..."
    api_provider = "..."
    model_name = os.getenv("OPENAI_MODEL")
    api_key = os.getenv("API_KEY")

# 装饰器 vs 函数式等价
register_template(
    MyAgent,
    name="my_agent",
    uuid="my-uuid",
    description="一句话说明用途",
)
activate_template("my_agent")
```

### 让 LLM 自己激活

Agent 自带 `activate_template(name)` / `deactivate_template(name)` / `list_templates(name="")` 三个 builtin_tool，LLM 可以在对话中根据需要动态管理模板池。

```python
agent.conversation("需要写文章的 Agent，先把 'writer' 模板激活")
```

## 旧写法（v0.3.0 起已弃用；`BaseAgent` / `AnthropicAgent` 直继承计划 v1.3.0 删除）

```python
@tangyuanAI.register_agent("my-uuid", "my_agent", "一句话说明 Agent 用途")
class MyAgent(tangyuanAI.BaseAgent):                            # noqa: v1.3.0 删除；用 Agent + protocol
    prompt       = "..."
    api_provider = "..."
    model_name   = "..."
    api_key      = "..."
```

**行为差异**：
- `@register_agent` 在 import 阶段就 `cls()` 实例化并写入 `agent_list`
- 模板池写法类只入池，运行时再激活

**迁移路径**：

```python
# 旧
@register_agent("uuid", "name", "desc")
class A(BaseAgent): ...

# 新（推荐）
@template_agent("name", uuid="uuid", description="desc")
class A(tangyuanAI.Agent):                       # ← 改用 Agent + protocol
    protocol = "openai"                         # ← 加 protocol 字段
activate_template("name")                       # 显式激活（或由 LLM 在对话中触发）
```

`@register_agent` 仍可用，调用时通过库内 `logger.warning(...)` 输出迁移提示。
`Agent_Base_.py` / `anthropic_agent.py` 模块**已 deprecated**（v1.0.0 起）；import 时打 `DeprecationWarning`，v1.3.0 删除。

## 子类必填类属性

每个 Agent 子类必须实现 4 个类属性（与协议无关）：

```python
class MyAgent(tangyuanAI.Agent):                  # 推荐写法：Agent + protocol
    protocol      = "openai"                     # "openai" | "anthropic" | "openai-responses"
    prompt        = "..."          # 系统提示词
    api_provider  = "https://..."  # 必填；缺则 _endpoint() 抛 ValueError
    model_name    = os.getenv("OPENAI_MODEL")  # 推荐走 os.getenv，不硬编码
    api_key       = os.getenv("API_KEY")
```

> 注：旧写法 `class MyAgent(tangyuanAI.BaseAgent): ...` 仍兼容（v0.4.2+），但已 deprecated。
> `_ProtocolMeta` metaclass 在类创建时根据 `protocol` 字段把 `Agent` 占位基类替换成
> `_OpenAIBase` / `_AnthropicBase` / `_OpenAIResponsesBase` 中相应的一个，运行时零开销。

## 模板池 API 速查

| 函数 | 作用 |
|---|---|
| `register_template(cls, name, uuid, description, overwrite)` | 把类登记到 `agent_template_pool` |
| `@template_agent(name, uuid, description, overwrite)` | 同上，装饰器语法 |
| `activate_template(name)` | 把池中 `cls` 实例化，按 `uuid` + `name` 双键写入 `agent_list` |
| `deactivate_template(name)` | 从 `agent_list` 移除实例，模板仍保留在池中 |
| `remove_template(name)` | 彻底从池中删除（连带从 `agent_list` 移除） |
| `list_templates()` | 列出全部模板 |
| `get_template(name)` | 查单个模板元信息 |
| `is_active(name)` | 模板是否已激活（`name in agent_list`） |

完整单测见 `tests/test_template_pool.py`（33 项）。