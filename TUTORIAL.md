# tangyuanAI 学习路径

> **从零到复杂 Agent 构建** —— 30 分钟跑通第一个,再按需深入。

tangyuanAI 是一个多协议 LLM Agent 框架,核心理念:**协议差异收拢到一个地方,你写一次 Agent 代码可以切任何 LLM**。

本教程按 5 个层级渐进,每层 5 分钟左右读完,所有 demo 都基于 **v1.3.0 API**(`agent.conversation(...)` / `agent.aconversation(...)`)。

---

## 学习路径

```
L1 基础 ────→ L2 入门 ────→ L3 中级 ────→ L4 进阶 ────→ L5 生产
5 分钟         10 分钟         30 分钟         60 分钟         按需
```

| 层级 | 章节 | 学完能 |
| --- | --- | --- |
| **L1 基础** | [01 getting-started](docs/tutorial/01-getting-started.md) | 跑通第一个 agent |
| | [02 protocols-and-agents](docs/tutorial/02-protocols-and-agents.md) | 一行切 OpenAI / Anthropic / Responses |
| **L2 入门** | [03 tools](docs/tutorial/03-tools.md) | 给 agent 装工具 + ACL |
| | [04 streaming-and-output](docs/tutorial/04-streaming-and-output.md) | 监听流式输出 / 钩子 |
| **L3 中级** | [05 persistence](docs/tutorial/05-persistence.md) | `.tas` 自动保存 / `addhistory=False` / 恢复 |
| | [06 multi-agent](docs/tutorial/06-multi-agent.md) | `ask_for_help` 跨 agent 调度 |
| | [07 skills-and-mcp](docs/tutorial/07-skills-and-mcp.md) | Skill 类化 + MCP 接入 |
| | [08 knowledge-base](docs/tutorial/08-knowledge-base.md) | RAG 检索 |
| **L4 进阶** | [09 a2a-interop](docs/tutorial/09-a2a-interop.md) | 本地暴露 A2A / 远端导入 |
| **L5 生产** | [10 production-patterns](docs/tutorial/10-production-patterns.md) | 协议链 / tracing / checkpoint / sandbox / eval |

---

## 每章统一结构

```markdown
# {N} {标题}

> 🎯 学完能做什么:{一句话}

## 概念(1 分钟)
## 5 行代码起步(可复制即跑)
## 完整 demo(指向 examples/)
## 进阶(链到 docs/)
## 常见问题(FAQ)
```

---

## 选择你想要的路径

- **"我只想跑通 demo"** → [01](docs/tutorial/01-getting-started.md) → [03](docs/tutorial/03-tools.md)
- **"我要接自己公司网关"** → [01](docs/tutorial/01-getting-started.md) → [02](docs/tutorial/02-protocols-and-agents.md) → [10](docs/tutorial/10-production-patterns.md)
- **"我要做 RAG"** → [01](docs/tutorial/01-getting-started.md) → [03](docs/tutorial/03-tools.md) → [08](docs/tutorial/08-knowledge-base.md)
- **"我要做多 Agent 协作"** → [01](docs/tutorial/01-getting-started.md) → [06](docs/tutorial/06-multi-agent.md)
- **"我要做生产级 Agent"** → [01](docs/tutorial/01-getting-started.md) → [10](docs/tutorial/10-production-patterns.md)

---

## 配套资源

- **完整示例**:`examples/example1-7.py`([目录](examples/))
- **API 文档**:`docs/`
- **迁移指南**:从旧版本升级?看 [MIGRATION.md](MIGRATION.md)
- **CHANGELOG**:`CHANGELOG.md`

---

> 💡 **建议**:跑通 [01](docs/tutorial/01-getting-started.md) 之后再决定要不要继续。30 分钟内能走完 L1+L2,这两个层级覆盖 80% 的日常用法。