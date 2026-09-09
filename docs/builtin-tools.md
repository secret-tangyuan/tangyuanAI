---
slug: builtin-tools
title: 内建工具
order: 5
icon: INVENTORY_2_OUTLINED
---

# 内建工具

> 每个 Agent 都自带 8 个内建工具（v0.3.0+ 4 个协作工具 + v0.3.0+ 4 个模板管理工具）。
> `BaseAgent` / `AnthropicAgent` 双协议一致。

无需手写 prompt 教 LLM 怎么调——框架已把工具描述注入到 system prompt 里。

## 协作工具（4 个）

| 工具 | 用途 | 适用场景 |
|---|---|---|
| `ask_for_help(agent_id, message)` | 委派任务给其他 Agent | Agent 间协作；走全局 `agent_queue` 防超限递归 |
| `list_agents()` | 列出所有已注册 Agent | 探索协作对象 |
| `attempt_completion(report_content="")` | 标记任务完成并退出对话循环 | 任务收尾 |
| `reload()` | 重新拉取工具/技能列表 + 刷新系统提示词（**保留对话历史**）+ 通知所有 reload 钩子 | 环境变更后想刷新；或自己改了 SKILL.md 想立即生效 |

### `ask_for_help` 队列机制

跨 Agent 调用走 `tangyuanAI.agent_queue.get_default_queue()`：

- **循环检测**：若 target 在当前调用链里直接拒绝
- **深度限制**：链长达到 `max_depth` 拒绝
- **串行执行**：worker pool 中每个 worker 一次只跑一个 Job

```python
from tangyuanAI.agent_queue import get_call_chain, get_default_queue

chain = get_call_chain()
queue = get_default_queue()
result = queue.submit(
    target_uuid=target_agent.uuid,
    call_fn=lambda: str(target_agent.conversation(message)),
    caller_chain=chain,
)
```

## 模板管理工具（4 个，v0.3.0+）

| 工具 | 用途 |
|---|---|
| `list_templates(name="")` | 查询模板池；name 为空则列出全部 |
| `activate_template(name)` | 把池中模板实例化并写入 `agent_list` |
| `deactivate_template(name)` | 从 `agent_list` 移除实例（保留在池中） |
| `register_template(name, description="")` | **占位说明**：注册 cls 必须在 Python 代码侧完成（工具调用只能传 JSON，无法注入 Python 类） |

### `register_template` 返回示例

```text
模板注册请在 Python 代码侧完成：
from tangyuanAI.Agent_list import register_template;
register_template(MyAgent, name='my_agent'。
当前 agent_template_pool 内的模板：writer、reviewer。
```

## 验证当前 Agent 可用工具

```python
tools = agent.get_all_available_tools()
# 返回 name 列表，包括：
# - ask_for_help / list_agents / attempt_completion / reload
# - list_templates / activate_template / deactivate_template / register_template
# - 所有 register_tool 注册的（按 ACL 过滤后）
# - 所有 @builtin_tool 装饰的方法
```

`get_all_available_tools` 走 ACL 过滤：只返回当前 agent 有权限的工具。

## 完整单测

`tests/test_anthropic_agent.py`（17 项）覆盖 `AnthropicAgent` 的全部 8 个 builtin_tool；
`tests/test_base_agent_parity.py`（6 项）覆盖 `BaseAgent` 同名工具；
`tests/test_template_pool.py`（33 项）覆盖模板池 API + `BaseAgent` 4 个 builtin_tool。