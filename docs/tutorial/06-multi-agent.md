# 06 Multi-Agent

> 🎯 学完能让多个 agent 互相调用,带循环检测和深度限制。

## 概念

`tangyuanAI.agent_list` 是一个全局注册表,agent 之间用 **`ask_for_help(agent_id, message)`** 内建工具互相调用。

- 调用走 `agent_queue` worker pool,**不爆栈**(递归深度可控)
- 自动 **cycle detection**(防止 A→B→A 死循环)
- 自动 **depth limit**(防止无限嵌套)

## 5 行代码起步

```python
@tangyuanAI.template_agent("researcher", uuid="r-1", description="调研员")
class Researcher(tangyuanAI.Agent):
    protocol = "openai"
    prompt = "调研一个主题,产出 3 个要点"

@tangyuanAI.template_agent("writer", uuid="w-1", description="写作员")
class Writer(tangyuanAI.Agent):
    protocol = "openai"
    prompt = "基于调研结果写写写文章"

# researcher 和 writer 都在 agent_list 上,writer 可以 ask_for_help("researcher", "...")
```

调用链示例(由调度器 / 一个 agent 触发):

```python
scheduler = tangyuanAI.agent_list["writer"]
result = scheduler.conversation(
    f"调研 AI 趋势然后写文章。{scheduler.ask_for_help('researcher', 'AI 趋势')}"
)
```

## 完整 demo

- [`examples/example3_multi_agent.py`](examples/example3_multi_agent.py) —— scheduler + researcher + writer 三 agent 协作

## 进阶

- [`docs/agent-registration.md`](../agent-registration.md) —— agent 注册与 `ask_for_help` 队列细节

## 常见问题

**Q: 跨 agent 调用怎么传上下文?**
A: `ask_for_help(agent_id, message)` 的 message 是字符串。如果要传结构化数据,把 JSON 序列化进 message 里。

**Q: 怎么防止某个 agent 太贵被反复调?**
A: 用 ACL(`allowed_agents=[...]`)限制谁能调它,或者用工具 `tool_max_workers` 限制并发。

**Q: 跨 agent 调用算进 history 吗?**
A: 各 agent 各管各的 history。`ask_for_help` 调度另一个 agent 时,它的 history 是独立的(从空开始),不会跟调用方合并。