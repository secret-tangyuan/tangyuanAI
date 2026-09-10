# 07 Skills and MCP

> 🎯 学完能让 agent 加载外部 Skill 模板,或接入 MCP(Model Context Protocol)服务。

## 概念

- **Skill** —— 用 SKILL.md 文件定义一组提示词 / 工具模板。tangyuanAI 自动发现 + 热加载,详见 [`docs/skill.md`](../skill.md)
- **MCP** —— Anthropic 的 stdio MCP 协议。tangyuanAI 桥接 MCP server,把它暴露的工具并入 `agent_list`,详见 [`docs/mcp.md`](../mcp.md)

## 5 行代码起步(Skill)

```python
import tangyuanAI
from tangyuanAI.skill import Skill

class TimeSkill(Skill):
    path = "/path/to/skills/time"     # SKILL.md 所在目录

tangyuanAI.skill_registry.register(TimeSkill())
agent = tangyuanAI.agent_list["weather"]
agent.conversation("现在几点了?")
```

## 5 行代码起步(MCP)

```python
import tangyuanAI
from tangyuanAI.mcp import MCPClient

class NotionMCP(MCPClient):
    server_path = "npx -y @notionhq/notion-mcp"   # stdio MCP server 启动命令

tangyuanAI.mcp_bridge.register(NotionMCP())
# 之后所有 agent 都能调 Notion 提供的工具
```

## 完整 demo

- [`docs/skill.md`](../skill.md) —— Skill 完整示例
- [`docs/mcp.md`](../mcp.md) —— MCP 完整示例 + `functions/api/` 集成

## 进阶

- [`docs/mcp-skills.md`](../mcp-skills.md) —— MCP 与 Skill 协作场景

## 常见问题

**Q: Skill 和 MCP 怎么选?**
A: Skill 是**提示词 / 模板**层(写 SKILL.md,定义提示词片段 + 工具描述);MCP 是**协议**层(stdio MCP server,通常是别人写好的服务)。两者互补——Skill 可以引用 MCP 暴露的工具。

**Q: Skill 能热加载吗?**
A: 可以。`Skill` 类支持 `watchdog` 监控目录变化,SKILL.md 改了自动 reload。