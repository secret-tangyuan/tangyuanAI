# 05 Persistence

> 🎯 学完能让 agent 状态自动保存 / 一次性 AI 调用不污染历史 / 中断恢复。

## 概念

tangyuanAI 默认在每次 `conversation()` / `aconversation()` 退出时自动把 agent 状态存到 `.tas` 文件(可换 sqlite 等后端)。无需手动保存。

**关键参数**(`conversation()` / `aconversation()` 都支持):

| 参数 | 默认 | 含义 |
| --- | --- | --- |
| `addhistory=True` | True | 是否把 user / assistant / tool_result 写入 history |
| `tooluse=True` | True | 是否派发 tools schema + 走 FC 续轮 |

`addhistory=False` 是 v1.3.0 新加的——做"不计入对话"的一次性 AI 调用(分类 / 路由 / 上下文增强),LLM 回复你拿得到,但 history 不留痕。

## 5 行代码起步

```python
import tangyuanAI
tangyuanAI.configure(auto_save=True)              # ← 默认就在最外层保存

agent = tangyuanAI.agent_list["weather"]
out = agent.conversation("北京天气?")              # 默认入 history,退出自动存
out = agent.conversation("分类这段文本", tooluse=False, addhistory=False)  # 一次性
```

## 手动恢复

```python
state = tangyuanAI.load_state(agent_uuid="weather-1")    # → dict
# 或:tangyuanAI.load_state(agent_name="weather")
new_agent = tangyuanAI.BaseAgent.from_state_dict(state)
new_agent.conversation("继续刚才的对话")                  # 接续 history
```

## 后端切换

```bash
# 文件后端(默认)
tangyuanai configure --backend file --base-dir ./sessions

# SQLite 后端
tangyuanai configure --backend sqlite --db-path ./sessions.db
```

## 完整 demo

- [`examples/example4_kb_basic.py`](examples/example4_kb_basic.py) —— 持久化与 KB 集成

## 进阶

- [`docs/persistence.md`](../persistence.md) —— `.tas` 文件格式 / 多后端 / 实时自动保存
- [`docs/conversation.md`](../conversation.md) —— `tooluse` / `addhistory` 详细语义

## 常见问题

**Q: 我的 agent 是批处理一次性脚本,不需要持久化怎么办?**
A: `tangyuanai configure --auto-save false` 关闭全局;或在 agent 上设 `auto_save=False`(per-agent)。

**Q: 多 agent 互相调(`ask_for_help`),持久化会不会冲突?**
A: 不会。框架用 `_conv_depth` 计数器保证递归调用只在最外层出口触发一次 `auto_save`。

**Q: `addhistory=False` 后,工具结果会进 history 吗?**
A: 默认不进。但若开了 FC(`tooluse=True`),工具调用过程中 `assistant(tool_calls)` 和 `tool(role)` 会进 history(FC 协议要求)。要彻底无痕用 `tooluse=False, addhistory=False`。