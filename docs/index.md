---
slug: index
title: 首页
order: 0
icon: HOME_OUTLINED
---

# tangyuanAI 文档

> 维护者：[secret-tangyuan](https://github.com/secret-tangyuan) · [个人介绍](https://gravatar.com/secrettangyuan)

tangyuanAI 是一个轻量、模块化的多智能体协作框架，让 LLM 像"公司团队"一样分工完成任务。

同一份 `agent_list` 同时容纳 **OpenAI 协议 Agent** 与 **Anthropic 协议 Agent**，通过 `Agent` 工厂基类 + `protocol` 字段统一选择（`BaseAgent` / `AnthropicAgent` 直继承仍兼容，但已 deprecated）。

## 文档导航

| 文档 | 内容 |
|---|---|
| [getting-started.md](getting-started.md) | 安装、API Key、第一个 Agent |
| [agent-registration.md](agent-registration.md) | 两种注册写法：模板池（推荐）vs `@register_agent`（弃用） |
| [tools.md](tools.md) | 工具注册：`@tool_registry.register_tool` vs `@builtin_tool` |
| [builtin-tools.md](builtin-tools.md) | 8 个内建工具一览（`ask_for_help` / `attempt_completion` / 模板管理等） |
| [protocols.md](protocols.md) | OpenAI 协议 vs Anthropic 协议、`Agent` 工厂基类、双协议对称性 |
| [output-and-hooks.md](output-and-hooks.md) | `pack` / `out` 输出事件总线、工具调用钩子 |
| [skill.md](skill.md) | Skill 类化：`class TimeSkill(Skill): path="..."` + SKILL.md 自动发现 |
| [mcp.md](mcp.md) | MCPClient 类：`class NotionMCP(MCPClient): server_path="..."` |
| [persistence.md](persistence.md) | Agent 状态持久化：`.tas` 文件格式 / 插件后端 / 实时自动保存 |
| [kb.md](kb.md) | 知识库（RAG）：Knowledge 类（多实例隔离）/ 全文 + 向量 + 重排检索 / 文档处理（v1.1.0+ vendor 在主包） |
| [a2a.md](a2a.md) | A2A 互操作（核心原生）：导入 / 导出 / 来源跟踪 |
| [image-generation.md](image-generation.md) | 图片生成：config 驱动的 provider 方言翻译 / 本地下载（v1.1.0+ vendor 在主包） |
| [image-input.md](image-input.md) | 图像理解（vision）输入：3 种传图方式 + Responses 协议 + `detail` 字段 |
| [plugin-install.md](plugin-install.md) | 第三方插件安装：`tangyuanai plugin install-git <git-url>` 或 `pip install <pkg>` |
| [plugin-dev.md](plugin-dev.md) | **插件开发 / 接口文档**：写兼容插件替换默认 KB / 图片实现 |
| [plugin-compat.md](plugin-compat.md) | 兼容外部 Plugin 协议（v1.1.1+）：OpenAI ChatGPT Plugin 1.0 + Anthropic Claude Code Plugin |
| [mcp-skills.md](mcp-skills.md) | MCP 与 Skill：跨进程通信 + 提示词 / 工具模板加载 |

> 本套文档就是本仓库自己搭的文档站：**https://ai.secret-tangyuan.com/docs**（Cloudflare Pages 构建，push 自动更新，见 [docs-site/README.md](../docs-site/README.md)）。

## 仓库结构

```
tangyuanAI/                       # 主包：tangyuanAI（PyPI）
├── Agent_Base_.py               # BaseAgent（OpenAI 协议）
├── anthropic_agent.py           # AnthropicAgent（Anthropic 协议）
├── Agent_list.py                # agent_list + 模板池（register_template / activate_template）
├── agent_tool.py                # @builtin_tool + tool_registry + ACL
├── agent_queue.py               # ask_for_help 跨 Agent 调用队列（防超限递归）
├── llm_transport.py             # HTTP transport 抽象 + OpenAI / Anthropic 实现
├── tool_runner.py               # 工具执行 ThreadPool + 超时转后台
├── http_utils.py                # 退避重试 HTTP 客户端
├── skill.py / skill_bridge.py   # Skill 注册 + 热加载
├── mcp_bridge.py                # stdio MCP 桥接
├── cli.py                       # `tangyuanai` CLI（Python 模块名 tangyuanAI）
├── docs/                        # 文档源（frontmatter 驱动，本套文档的 markdown 源）
│   ├── index.md                 # 本页（slug: index, order: 1）
│   ├── getting-started.md
│   └── ...                      # 每篇 .md 顶部有 YAML frontmatter（slug/title/order/icon）
├── docs-site/                   # 文档站（VitePress + Pages Functions，不入 PyPI 包）
│   ├── .vitepress/              # 配置 + BBDDFF 浅蓝主题
│   ├── scripts/                 # sync-docs / generate-api-data（构建前）
│   ├── functions/api/           # Cloudflare Pages Functions（/api/*）
│   ├── api/                     # FastAPI 后端（本地 dev 演示）
│   ├── public/_redirects        # SPA 回退
│   └── README.md                # 文档站启动 / 部署说明
└── tests/
    ├── _llm_mock.py             # OpenAI + Anthropic 协议 mock（v0.3.1+）
    ├── test_anthropic_agent.py  # Anthropic 协议层端到端单测
    ├── test_base_agent_parity.py# BaseAgent / AnthropicAgent 对称性单测
    ├── test_template_pool.py    # 模板池 API 单测
    ├── test_agent_queue.py      # ask_for_help 队列单测
    └── ...
```

## 核心约定

- **双键 agent_list**：`agent_list[uuid]` 和 `agent_list[name]` 命中同一实例。
- **XML 标签协议**：Agent ↔ Agent、Agent ↔ Tool 走 `<ask_for_help>` / `<attempt_completion>` 等 XML 标签（除非 `fc_model=True` 走原生 function calling）。
- **工具 ACL**：`register_tool(allowed_agents=[...])` 显式列出允许的 agent；`None` / `[]` 表示全局可用。
- **`allowed_agents` 用 agent name 不用 uuid**（`check_permission` 内部会做 uuid→name 翻译，详见 [tools.md](tools.md#acl-注意事项)）。