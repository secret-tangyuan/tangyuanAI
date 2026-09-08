# Changelog

tangyuanAI 的所有显著变更记录。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- **`conversation` / `aconversation` 新主入口 + `tooluse` / `addhistory` 参数**
  - `agent.conversation(messages, *, tooluse=True, addhistory=True, images=None)` —— 替代 `conversation_with_tool` 的统一对话入口
  - `agent.aconversation(...)` —— 异步版
  - `tooluse=True`（默认）：是否派发 tools schema + 是否允许 FC 递归；`False` 时关闭 tool 能力
  - `addhistory=True`（默认）：是否把 user / assistant / tool_result 写入 `agent.history`；`False` 时实现"不计入对话"的一次性 AI 调用（分类 / 路由 / 上下文增强）
  - 新测试 `tests/test_conversation.py`（9 项）覆盖默认行为、`addhistory=False`、 `tooluse=False`、async 版、alias 兼容性

### Changed
- **内部 `tool` 标记合并进 `addhistory` 语义**：旧 `tool=True` 的"FC 续轮"标志不再外露；新的内部 FC 续轮直接调 `self.conversation()`（默认参数），更直观。
- 文档 / examples / 内部 `ask_for_help` 全部切到新名 `conversation`

### Deprecated
- **`conversation_with_tool` / `aconversation_with_tool` 软重命名**：保留为 deprecated alias，调时打 `DeprecationWarning`。
  - 内部 `a2a_client.A2AAgentProxy` 同款保留 alias
  - **计划 v2.0 移除**（v1.3.0 起 deprecate）

### Migration
```python
# 旧
agent.conversation_with_tool("hi", tool=True)

# 新（默认行为等价）
agent.conversation("hi")

# 新（一次性 AI 调用，不入历史）
agent.conversation("分类这段文本", tooluse=False, addhistory=False)
```

## [1.1.1] - 2026-08-15

> 完整代码审查 + bug fixes + 兼容外部 Plugin 协议（OpenAI ChatGPT Plugin 1.0 + Anthropic Claude Code Plugin）。
> v1.1.1-rc1 已发布（代码 fixes + deprecation 预告），本版新增 plugin 重构。

### Added
- **外部 Plugin 协议兼容**（`tangyuanai.plugin` 子包，约 500 行新代码）：
  - `plugin/manifest.py`：统一的 `PluginManifest` pydantic 模型，覆盖 OpenAI ChatGPT Plugin 1.0（`name_for_model` / `api` / `auth`）+ Anthropic Claude Code Plugin（`name` / `version` / `skills_dir` / `hooks`）。`detect_protocol()` 自动识别协议。
  - `plugin/fetcher.py`：
    - `HTTPFetcher(base_url)`：拉 `https://<host>/.well-known/ai-plugin.json` + OpenAPI spec
    - `LocalFetcher(path)`：读 `<plugin>/.claude-plugin/plugin.json`
    - `GitHubSource(name)`：旧中央仓库 `<name>.json`（向后兼容，v1.3.0 删）
  - `plugin/openapi.py`：OpenAPI 3.0 spec → tool schema 转换器，支持 `openai_chat` / `openai_responses` / `anthropic` 三种输出格式。`validate_spec=True` 触发 `openapi-spec-validator` 校验。
  - `plugin/loader.py`：统一 `load_plugin(target)` 入口，sub-component 加载**复用既有模块**（skills → `skill.py`、MCP → `mcp_bridge.py`），不重写 SKILL.md / MCP 解析逻辑。
  - 新 CLI 子命令：`tangyuanai plugin load <path|url> [--schema-format ...]`
  - 新顶层 API：`load_external_plugin(target)`，`__init__.py` re-export
- **新依赖**：`openapi-spec-validator>=0.7`（可选 OpenAPI 3.0 spec 完整性校验）
- **新文档**：`docs/plugin-compat.md`（OpenAI / Anthropic 双协议详解）
- **新测试**：`tests/test_external_plugin.py`（22 项）—— manifest 解析、HTTP / Local fetcher、OpenAPI 转换、端到端 Anthropic plugin 加载

### Changed
- **`Agent + protocol` 工厂基类正式成为推荐写法**：
  - `docs/agent-registration.md`、`docs/getting-started.md`、`docs/protocols.md`、`docs/output-and-hooks.md` 默认示例全部 `Agent + protocol`
  - `examples/example1-5` 改为 `class X(tangyuanAI.Agent): protocol = "openai"`
  - `examples/example6_anthropic_custom_provider.py` 改为 `class X(tangyuanAI.Agent): protocol = "anthropic"`
  - `examples/example7_unified_agent.py` 保留旧写法对比，但推荐路径用 `Agent + protocol`
  - `agent_tool.py` docstring 示例同步

### Fixed（完整列表见 v1.1.1-rc1 段）
v1.1.1-rc1 已合并所有修复；本版（v1.1.1 final）无新增修复。

### Deprecated
- **`Agent_Base_.py` / `anthropic_agent.py`**：再 deprecate 一次，**计划在 v1.3.0 删除**（v1.0.0 起已 deprecation，本版升级文案）
- **`BaseAgent` / `AnthropicAgent` 直继承**：仍兼容（v0.4.2+），但**强烈推荐**改用 `Agent + protocol`
- **旧 plugin 格式**（`tangyuanai.plugins` entry point + `<name>.json` 中央仓库）：仍兼容，**计划 v1.3.0 删除**。新代码用 `tangyuanai plugin load <path|url>`。

### Tests
- `uv run ruff check .` → All checks passed
- `uv run pytest -q` → **253 passed, 2 skipped**（v1.1.0: 232 + 新增 21）
- rollback 锚点：commit `a03eaba`（v1.1.1 之前的最后状态），tag `rollback-pre-fix-v1.1.1`
- 预发布 tag：`v1.1.1-rc1`（仍在 GitHub 可用）

### Upgrade
```bash
pip install --upgrade tangyuanAI==1.1.1
```

旧 API 全部兼容；可直接升级：
- `from tangyuanAI.BaseAgent` → 仍可用，但建议改 `from tangyuanAI.Agent` + `protocol = "openai"`
- `from tangyuanAI.anthropic_agent import AnthropicAgent` → 仍可用（v1.3.0 删），建议改 `from tangyuanAI.AnthropicAgent`（始终指向 `_AnthropicBase`）+ `protocol = "anthropic"`
- 旧 plugin entry point 仍可用（v1.3.0 删）；新代码用 `tangyuanai plugin load <path|url>` 识别 OpenAI / Anthropic 外部 manifest

---

## [1.1.1-rc1] - 2026-08-14

> 严格审查 + 兼容性补丁 + 弃用预告。`Agent + protocol` 工厂基类正式成为推荐写法。
> 完整 plugin 重构（Anthropic Claude Code Plugin + OpenAI ChatGPT Plugin 1.0 双识别）
> 见 [v1.2.0 计划](#120---)。

### Fixed
- **`llm_transport.py` Responses SSE bytes/str 不匹配 bug**：`_process_responses_sse_line` 用 `line.startswith(b"data: ")` 配 `httpx.Response.iter_lines()` 返回的 `str`，直接 `TypeError`。现改为 `str`；同步把 `_ResponsesSSEState.tool_call`（单 dict）改成 `tool_calls: list` + `_current_idx`，单轮 Responses API 可发多个 function_call 不再互相覆盖。
- **`agent.py` `out()` 吞 `tool_result` 事件**：之前 `tool_result` 事件因带 `tool_name` 字段被第一分支命中后直接 `return`，结果内容从未打印；现 `tool_result` 优先匹配，新增 `[工具结果] name → result` 输出。
- **`agent.py` `pack(finish_task=True)` 误发于 usage 事件**：`usage` 只是模型流尾附带的 token 计数，**不是终止信号**；`pack(finish_task=True)` 会误打 `[完成]`。stream / 非流式两条路径都改为只在 `evt.type == "done"` 或对话真正结束时打 finish_task。
- **`agent.py` f-string 漏空格**：`f"no return for the tool{tool_name}"` → `f"no return for the tool {tool_name}"`（之前输出 `"...toolfoo"` 这种粘连）。
- **`agent.py` XML 模式正则不匹配中文工具名**：`<(\w+)>` 的 `\w` 不含中文；改为 `[\w一-鿿㐀-䶿]+` 支持中文工具名。
- **`agent.py` XML 分支 TypeError 漏 catch**：第一分支（`has_kwargs or param_count == 0`）的 `tool_func(**params)` 不在 try 里，现补上。
- **`agent.py` `_collect_stream_events` 收到 `done` 不结束循环**：原代码收到 `usage` 就 `stream_run=False` 后还在等下一帧，新加 `evt.type == "done"` 分支显式处理。
- **`agent.py` `_OpenAIResponsesBase` 复用 OpenAI Chat Completions ping**：之前 `_ping_endpoint` 走 Chat Completions，但 Responses API endpoint 是 `/v1/responses`，ping 必失败；新增 `_ping_endpoint` / `_ping_payload` override。
- **`agent.py` `_connectivity` 后台线程泄漏 `HTTPClient`**：每个 Agent 都 `new HTTPClient()` 但永不 `close()`；加 `finally` 关闭连接池。
- **`agent.py` `os_main_folder` 未知平台 AttributeError**：BSD / AIX 等平台未赋值；加 `else: os.path.expanduser("~")` 兜底。
- **`agent.py` 工具结果回填遍历 `tool_results` 用 `n` 索引 parallel 遍历 `tool_names`**：用 `zip(tool_names, tool_results)` 替代，无对齐错位风险。
- **`errors.py` `__getattr__` 弃用提示文案反的 bug**：`TangyuanConnectionError` / `TangyuanTimeoutError` 的 `DeprecationWarning` 提示文案原本指向「自己」（copy-paste bug）；现改为指向 `ConnectionError` / `TimeoutError`（`APIError` 子类）。
- **`errors.py` 删无意义自赋值 + 死变量**：删 `TangyuanError = TangyuanError`（no-op）和 `_OLD_NAME_USED = {"__init__"}`（从未引用）。
- **`mcp_bridge.py` 模块级 `asyncio.Lock()` import 期创建**：Python 3.10+ 不推荐；改为 `_get_session_lock()` 懒初始化。
- **`mcp_bridge.py` `asyncio.get_event_loop()` 过时**：3.10+ `DeprecationWarning`，3.12+ `RuntimeError`；先 `get_running_loop()`，fallback 才走 `_event_loop`。
- **`mcp_bridge.py` `list_resources` 不存在时整个 init 失败**：MCP 规范允许 server 不实现 resources；现 try/except 后置空 `resources`。
- **`mcp_bridge.py` `start_health_check / stop_health_check` 在已有 running loop 的线程里跑会 raise**：先 `get_running_loop()`，fallback 才用模块级 loop。
- **`a2a_client.py` `send_task_sync` / `register_a2a_agent` 在已有 running loop 时炸**：用 `concurrent.futures.ThreadPoolExecutor(max_workers=1)` 在子线程跑 `asyncio.run`；主线程 blocking 等结果。
- **`a2a_exporter.py` `tasks/sendSubscribe` 与 `tasks/send` 走同一个 sync handler（sse 流假实现）**：现拆为 `handle_tasks`（普通 JSON）和 `handle_tasks_subscribe`（SSE chunk）。
- **`Agent_list.py` `deactivate_template` 不清 `_agent_sources`**：之前 deactivate 后 `_agent_sources` 残留；现同步 pop 两个 key。
- **`cli.py` `cmd_plugin_status` 用 `"mod" in dir()` 判断 import 成功**：脆弱；改为 `mod = None` 显式跟踪。
- **`kb/embedder_base.py` 无意义 `get_logger` wrapper**：删，直接 `from tangyuanAI.logging_config import get_logger`。
- **`tool_runner.py` `_Task.arguments` 只存 kwargs 不存 args**：`get_status(task_id)["arguments"]` 拿不到位置参数；加 `args: tuple = ()` 字段。
- **`anthropic_agent.py` `if new_load: self.history = [] else: self.history = []`**：两分支相同；加注释说明「else 分支历史走持久化恢复，迁移到 `persistence.load_state()` 后 init 不再做；保留为兼容子类覆写」。

### Deprecated
- **`Agent_Base_.py` / `anthropic_agent.py`**：从 v1.0.0 起已 deprecation；**计划在 v1.3.0 移除**。DeprecationWarning 文案升级：
  ```
  tangyuanAI.Agent_Base_ 已弃用；**计划在 v1.3.0 删除**。新代码请用 tangyuanAI.BaseAgent。
  ```
- **`BaseAgent` / `AnthropicAgent` 别名**：保留作为 `tangyuanAI.BaseAgent` / `tangyuanAI.AnthropicAgent`（始终指向 `_OpenAIBase` / `_AnthropicBase`）的过渡别名；`BaseAgent` / `AnthropicAgent` 直接继承仍兼容（v0.4.2+），但**强烈推荐** `Agent + protocol` 写法。

### Changed
- **README + docs + examples 推荐写法统一为 `Agent + protocol`**：
  - `examples/example1-5`：`BaseAgent` → `Agent` + `protocol = "openai"`
  - `examples/example6_anthropic_custom_provider.py`：`AnthropicAgent` → `Agent` + `protocol = "anthropic"`
  - `examples/example7_unified_agent.py`：保留旧写法对比，但所有推荐路径都用 `Agent + protocol`
  - `examples/README.md`、`docs/agent-registration.md`、`docs/getting-started.md`、`docs/protocols.md`、`docs/output-and-hooks.md`：默认示例全部 `Agent + protocol` 写法
  - `agent_tool.py` docstring 示例同步
- **`anthropic_agent.py` `_AnthropicBase`（兼容壳）`pack / out / 8 个 builtin_tool` 仍兼容**；推荐迁移见 `tangyuanAI.AnthropicAgent`（始终指向 `_AnthropicBase`）。

### Verified
- `uv run ruff check .` → All checks passed
- `uv run pytest -q` → **232 passed, 2 skipped**（aiohttp 未装，2 个 a2a 测试 skip），无回归
- rollback 锚点：commit `a03eaba`（v1.1.1 之前的最后状态），tag `rollback-pre-fix-v1.1.1`

---

## [1.1.0] - 2026-08-13

> 知识库（RAG）与图片生成 **vendor 回主包 + 第三方可替换**：
> 默认实现进主仓（单 wheel 体验，零 `@git+`），`tangyuanAI.kb` / `tangyuanAI.imaging` 是
> bridge（有 vendored fallback，第三方 entry point 可接管）。

### Added
- **vendor 默认（v1.1.0+）**：
  - `tangyuanAI/kb/` 完整 KB 实现（51 .py）+ `tangyuanAI/imaging/` 图片生成（generator + provider）全部进主包。
  - `kb/__init__.py` / `imaging/__init__.py` 是 bridge：先查 `tangyuanai.plugins` entry point；
    找到用 `install_module_alias` 接管命名空间；没装第三方直接 import vendored 子模块（fallback）。
  - 核心 `dependencies` 加回 KB / Image 依赖（qdrant-client / unstructured /
    langchain-text-splitters / tenacity / msgpack / tiktoken / lxml）。
- **第三方插件安装路径**（推荐）：
  - 新增 `tangyuanai plugin install-git <git-url>` 子命令（`--branch` / `--dir` / `--editable`），
    内部走 `uv pip install git+...@branch[#subdirectory=...]`。
  - 兼容原 `pip install <pkg>`：第三方包按 `tangyuanai.plugins` entry point 规范注册即可接管默认。
- **接口文档**：`docs/plugin-install.md` 重写（CLI install-git 为推荐路径）；
  `docs/plugin-dev.md` 保留（写兼容插件的入口契约）。
- **官方子仓**保留作可选 git 装源：[tangyuanAI_RAG_plus](https://github.com/secret-tangyuan/tangyuanAI_RAG_plus) /
  [tangyuanAI_image_plus](https://github.com/secret-tangyuan/tangyuanAI_image_plus)（**不再上 PyPI**）。

### Changed
- 移除 `pyproject.toml` 的 `[kb]` / `[image]` / `[all]` @git+ extras（避免解析冲突、保持单 wheel 体验）。
- `cmd_plugin_status` 加上 `KB / Image 子系统: vendored 默认实现 vs 第三方插件接管` 状态展示。
- `tangyuanai.kb` / `tangyuanai.imaging` 重新有实现（不再纯桥），但保留插件扩展点（entry point 接管）。

### Removed
- 删 `tests/kb/`、`tests/test_image_generation.py`、`tests/_fake_imaging_provider.py`
  （KB / Image 测试在各自的子仓跑，避免主仓测试矩阵臃肿）。

## [1.1.0-alpha] - 2026-08-13

> 知识库（RAG）与图片生成**插件化**：实现迁移到独立插件包，核心通过 entry point 发现/替换；
> 新增插件接口文档与 `tangyuanAI[all]` 一键安装。

### Added
- **插件架构（v1.1.0-alpha）**：
  - 新增 `tangyuanai/plugin_api.py` + `tangyuanai/plugin_loader.py`：`tangyuanai.plugins` entry point 发现、惰性加载、命名空间桥接（`tangyuanAI.kb` / `tangyuanAI.imaging`，含深层子模块别名）。
  - 新增 `tangyuanai plugin status` 子命令；`plugin install` 支持已知插件名自动匹配中央仓库、已安装代码包内置 config 离线安装。
  - `pyproject.toml` 新增 extras：`tangyuanAI[kb]` / `tangyuanAI[image]` / `tangyuanAI[all]`（git 安装两个官方插件包）。
  - 新增接口文档 `docs/plugin-dev.md`：插件级契约（entry point）+ 能力级契约（Protocol）+ 中央 config 仓库发布流程。
- **官方插件包**：
  - [tangyuanai-rag-plus](https://github.com/secret-tangyuan/tangyuanAI_RAG_plus)：知识库 / RAG（原 `kb/` 实现迁移；`PLUGIN_TYPE=knowledge_base`；重依赖不再随核心安装；provider extras 随之迁移）。
  - [tangyuanai-image-plus](https://github.com/secret-tangyuan/tangyuanAI_image_plus)：图片生成（原 `imaging/` 实现迁移；`PLUGIN_TYPE=image_generation`；含中央仓库 config JSON）。

### Changed
- `tangyuanAI.kb` / `tangyuanAI.imaging` 从"捆绑实现"改为"命名空间桥"：插件装好后行为不变，未装时给出安装提示。
- **A2A 保持核心原生**：`tangyuanAI.a2a_client` / `a2a_exporter` / `a2a_protocol` 迁到顶层模块（原 `kb/a2a_*`），不随 RAG 插件迁移。
- 核心 `dependencies` 移除 KB 重依赖（qdrant-client / unstructured / langchain-text-splitters / tenacity / msgpack / tiktoken / lxml）。
- 核心 `kb-*` 可选依赖 extras 迁移到 `tangyuanai-rag-plus`；`a2a` extra 保留在核心（A2A 核心原生支持）。
- `tests/kb/`、`tests/test_image_generation.py` 迁移到对应插件仓库（各自带 CI）。

### Removed
- 核心不再捆绑 `kb/` 与 `imaging/` 实现代码（保留桥接 `__init__.py`）。


## [1.0.1] - 2026-08-07

> v1.0.0 之后的新增与改进。主要是 Knowledge Base / RAG 子系统、Image Generation 子系统、类化重构（Knowledge / Skill / MCPClient）、A2A 互操作，以及文档补齐。

### Added
- **Knowledge Base / RAG 子系统（kb/ 包）**：完整 RAG 检索增强生成能力。
  - 混合检索：Qdrant dense（向量）+ sparse（BM25）+ RRF 融合；embedded 默认 + 可切 server。
  - 嵌入模型：OpenAI / Cohere / Jina / Voyage / 任何 OpenAI-compatible 端点（Ollama / vLLM / Xinference / LM Studio / 私网关）；**不硬编码模型列表**，用户指定 provider + api_base + model + embed_dim。
  - 重排模型：NoOp / Cohere / Jina / BGE（本地）/ ColBERT / MonoT5；token-aware 批处理 + 重试 + 缓存。
  - 文档处理：unstructured（默认）/ minerU（学术 PDF）/ open minerU / Paddle OCR / raw；按扩展名自动派发，preferred 可覆盖。
  - 生产级：嵌入缓存（进程内 LRU 10k + 磁盘 SQLite + msgpack 压缩，懒重连）；token-aware 批处理；失败重试；维度校验；模型迁移（原子 swap：建新 collection → re-embed → swap → 删旧）；持久化（SQLite WAL）；日志（复用 `logging_config`）；HTTP 复用 `http_utils`。
  - 顶层 API（async + sync 包装）：`register_kb` / `get_kb` / `list_kbs` / `delete_kb` / `add_document` / `add_documents` / `search` / `migrate_embedding_model` / `register_kb_tools`。
  - CLI：`tangyuanai kb {add,search,list,show,delete,migrate,providers,processors,cache}` 9 个子命令。
  - 工具集成：`register_kb_tools(kb)` 注册 `kb_<name>_search / _list / _add` 给 Agent 用。
  - 多文件拆分：每个 provider 一个文件（`kb/embedder_openai.py` 等），新增 provider = 加 1 文件 + factory 1 行，**不动其他文件**。
- **Knowledge 类**（替代全局 `_kbs` dict）：`class MyKB(Knowledge): embedder=...; chunk_size=...` → 实例化多 KB、完全隔离（独立 collection + 独立 meta DB + 独立 id）、AI 可直接持有实例调 `kb.add()` / `kb.search()` / `kb.migrate()` / `kb.register_tools()`。`register_kb/get_kb` 薄包装向后兼容。
- **Skill 类化**：`class TimeSkill(Skill): path="./skills/time"` → 实例化自动从 SKILL.md 解析 name/description/parameters 并自动注册到共享 skill 池。新增 `Skill.from_dir()`。
- **MCPClient 类**：`class NotionMCP(MCPClient): server_path="..."` → `async with NotionMCP() as m: tools = await m.list_tools()`；`m.register_tools()` 注入 Agent。
- **A2A 互操作**：
  - 导入：`discover(url)` / `register_a2a_agent(url)` → `A2AAgentProxy` 注册到 agent_list，`ask_for_help` 透明调远端。
  - 导出：`A2AExporter(host, port)` 暴露 `/.well-known/agent.json` + `POST /a2a/v1/tasks/send`（aiohttp，optional `[a2a]`）。
  - 来源跟踪：`register_agent(name, instance, *, source="internal"|"a2a:<url>")` + `agent_source()` / `list_internal_agents()` / `list_external_agents()`。
- **Image Generation 子系统（config-driven）**：
  - 通用 `HttpJsonImageProvider`：读 config 的 `request_template`（`${var}` 占位符）+ `response_image_url_path`（JSON path）→ **每家 provider 自己的"方言"在 config 描述，新增 provider 不写 Python**。
  - 内置 SiliconFlow（flat body）+ DashScope / 阿里百炼（nested OpenAI chat body + `${env:VAR}` URL 占位）模板。
  - 本地下载：`download=True` 自动落盘（URL 1 小时过期）。
  - CLI：`tangyuanai image-gen "prompt" [--download] [--image-size] [--model] ...`。
  - Plugin：`tangyuanai plugin install <name>` / `plugin list`，从中央仓库 `https://github.com/secret-tangyuan/tangyuanAI_image_plus` 下载配置合并到 `tangyuanai.config.json`。
  - `tangyuanai.config.json`：`features` 列表（name / type / enabled / config），路径 cwd → `$TANGYUAN_CONFIG`。
  - 工具：`render_template` / `resolve_json_path` / `resolve_url_template` / `download_urls`。
  - **通用传输旋钮**：`auth_scheme` / `auth_header` / `auth_prefix`（默认 `Authorization: Bearer`；厂商用 `X-API-Key` 等只需 config 改 2 行）+ `request_static` / `timeout`。
  - **传输差异插件**：`provider_impl: "module:ClassName"` 覆盖 form-data / base64 / 自定义鉴权等（实现 `ImageProvider` Protocol，不需要改核心）。
  - 内置适配：SiliconFlow / DashScope / MiniMax（`data.image_urls` 数组响应）。

### Changed
- **KB 子包结构重组**：50 个 `kb_*.py` 文件统一移到 `kb/` 子包，文件名去掉 `kb_` 前缀（子包名已表明是 KB）。`knowledge_base.py` → `kb/__init__.py`；`kb_cli.py` → `kb/cli.py`；测试移到 `tests/kb/`。
  - 新增 KB provider 路径明确：建 `kb/<area>_<provider>.py` + factory dict 1 行，**不动其他文件**。
  - 外部 import 路径：`from tangyuanAI.kb_X import ...` → `from tangyuanAI.kb.X import ...`。
  - `tangyuanAI` 顶层 + `kb/` 子包均导出 KB API（向后兼容：用户写 `from tangyuanAI import register_kb` 仍可用）。
- **弃用 OpenAI SDK，httpx 自建适配**：`kb/embedder_openai.py` 改用 `http_utils.AsyncHTTPClient`（httpx）；修 `/v1` 重复前缀 bug（base_url 含 /v1 时不再 `/v1/v1/rerank`）；`pyproject.toml` 删 `openai` required 依赖。
- **`docs/kb.md` 同步**：更新所有 import 路径 + 架构图（`kb/loader_*.py` 等新路径）；厂商中立化（不绑定具体 vendor）。
- **`pyproject.toml`**：`packages` 加 `"tangyuanAI.kb"`；新增 `[a2a]` extra。
- **新增文档**：`docs/a2a.md`（A2A 互操作）；`docs/skill.md`（Skill 类化）；`docs/mcp.md`（MCPClient 类）；`docs/image-generation.md`（图片生成子系统）；`docs/plugin-install.md`（plugin 安装）。
- **`docs/index.md`**：文档站新增 skill.md / mcp.md / image-generation.md / plugin-install.md 条目。
- **文档站整合落地页（docs-site）**：`/` 变成落地页（`landing/`，BOLD-MINIMAL 设计系统，深浅色跟随系统 + 手动切换），文档迁移到 `/docs/*`；`sync-docs.mjs` 同步到 `docs-build/docs/`，`generate-api-data.mjs` 相应改读该目录；启动命令不变（`pnpm dev` → `http://localhost:5173`）。顺手修：frontmatter 解析兼容 CRLF（侧栏标题不再显示原始文件名）、主题 CSS 首行笔误、补 `public/logo.svg`。

### Fixed
- **CI 失败**：`openmineru>=0.1` 在 PyPI 上不存在，导致 `uv sync` 解析失败。已从 `[project.optional-dependencies]` 移除 `kb-processor-openminerU`（provider 代码保留在 `kb/doc_processor_openmineru.py`，需手动从源码安装）；`ruff check .` 215 个错误（E401/F401/F841/I001/W292）已清理，`uv sync` / `ruff` / `pytest` 全绿。

## [1.0.0] - 2026-08-05

> 首次 PyPI 发布。从 `dumplingsAI` 改名 `tangyuanAI` 是 breaking change：Python import / CLI 命令 / 环境变量 / .gitignore 目录名 / `.tas` 格式头全部更新。

### Added
- **协议无关的 Agent 工厂**（v0.4.2+ → 1.0.0）：`tangyuanAI.Agent`（带 `protocol` 字段）做工厂基类，靠 `protocol = "openai" / "anthropic" / "openai-responses"` 一行切协议；自带 8 个内建工具（`ask_for_help` / `list_agents` / `attempt_completion` / `reload` / `list_templates` / `activate_template` / `deactivate_template` / `register_template`），`BaseAgent` / `AnthropicAgent` 双协议对齐。
- **`register_protocol(name, base_cls)` / `list_protocols()`**：第三方扩展协议——实现 `LLMTransport` 后调一次注册就能用。
- **OpenAI Responses API 支持**（v0.4.2+）：`HttpxOpenAIResponsesTransport` 走 `/v1/responses`，非流式 / 流式双路径。
- **LLM Transport 抽象层共享 SSE 状态机**（v0.4.2+）：OpenAI / Anthropic / Responses 三协议的 sync+async SSE 解析器各合并为一套状态机 + 单行处理函数，消除 ~250 行重复。
- **CLI 子命令**（v1.0.0+）：`tangyuanai agent/tool/skill/mcp/session/config/run` 完整子命令，覆盖 Agent 管理、工具列表、Skill 列表、MCP 会话、持久化 session、运行等场景。
- **协议常量**（v0.4.2+）：`OPENAI` / `ANTHROPIC` / `OPENAI_RESPONSES` / `openai` / `anthropic` / `openai_responses`，让 `agent.protocol = OPENAI` 不需要打引号。
- **`enable_connectivity` 类属性**（v1.0.0+）：关闭 Agent 的后台连通性 ping（默认开启；测试/离线开发可关）。
- **Agent 状态持久化（v0.4.0+ → 1.0.0）—— 可插拔后端架构**
  - 自定义 `.tas` 文件格式（INI 头 `[META]/[CONFIG]/[STATE]` + JSONL 体 `[HISTORY]`）：人类可读 / git diff 友好 / 可手编，`schema_version` 自动从 `tangyuanAI.__version__` 读，pyproject bump 自动同步。
  - 顶层 API：`save_state(agent, key, *, backend=None)` / `load_state(key, *, backend=None)` / `delete_state` / `list_states` / `export_state_string(agent)` / `load_state_string(s)`。
  - 内置后端：`FileBackend`（默认）、`SQLiteBackend`（**实验性**）。
  - 插件协议 `PersistenceBackend`（save/load/delete/list_keys）+ `register_backend` 注册自定义后端（Redis/Postgres/S3）。
- **实时自动保存**：`TANGYUAN_PERSISTENCE*` 环境变量 + `tangyuanAI.configure(enabled=, ...)` API，`@_auto_save` / `@_auto_save_async` 装饰器用 `_conv_depth` 计数器保证最外层调用退出时保存一次，FC 模式递归不重复。

### Changed
- **包名 / import / CLI / env 全替换**：`dumplingsAI` → `tangyuanAI` / CLI `dumplings` → `tangyuanai` / `DUMPLINGS_*` → `TANGYUAN_*` / `.tas` 格式头 `duagent-state` → `tangyuan-state`。
- **GitHub 仓库**：`Secret-Dumplings/dumplingsAI` → `secret-tangyuan/tangyuanAI`。
- **协议无关 Agent**：`Agent`（含 `protocol` 字段）替代直接继承 `BaseAgent` / `AnthropicAgent` 选用基类；新增 `OPENAI` / `ANTHROPIC` / `OPENAI_RESPONSES` 常量。
- **公共类名**：`DumplingsError` → `TangyuanError`（保留 alias）；`DumplingsConnectionError` / `DumplingsTimeoutError` → `Tangyuan*`（保留 deprecation alias）；`__dumplings_template__` → `__tangyuan_template__`。
- **轻量化**（~250 行重复消除）：`_dispatch_tool` / `_build_user_message` / `_extract_system_and_messages` / `_collect_tools_schema` / `_connectivity` / Anthropic sync+async `conversation_with_tool` 全部上提 `_AgentCommon` mixin 默认实现；OpenAI / Anthropic SSE 解析改为共享状态机 + 单行处理函数（sync/async 只差迭代器）。
- **兼容壳**（过渡兼容，不删除旧路径）：`Agent_Base_.Agent` / `anthropic_agent.AnthropicAgent` 走 `DeprecationWarning` re-export 引导用户迁移。
- **examples 全部迁移**（Tangyuan/examples/example1-7 + 主仓 examples/）从旧 `@register_agent` 装饰器形态迁到 `@template_agent + activate_template` 模板池模式。
- **README 重写**（中文优先 + 英文辅助翻译）：痛点驱动叙事（"LLM 协议差异收拢到一个 transport 层"）+ 一段协议 vs 100+ 行对比（A2A 客户端手写 vs tangyuanAI `ask_for_help`）+ schema 手写 vs 函数签名对比（**不用写 function 的 schema**）。
- **文档站**：[https://docs.ai.secret-tangyuan.com/](https://docs.ai.secret-tangyuan.com/)（Cloudflare Pages 部署，VitePress）；README + docs 加 `secret-tangyuan` / [gravatar](https://gravatar.com/secrettangyuan) byline。

### Fixed
- **`agent.py` 文件底部重复块清理（import crash 修复）**：之前 `register_protocol("openai-responses", _OpenAIResponsesBase)` 在类定义之前执行导致 `NameError`，整个包无法 import。合并后改用单行 import + 三协议统一注册。
- **`mcp_bridge` 双会话池 bug**：模块级 `MCP_SESSION_POOL` 与 `MCPSessionPool._pool` 是两个独立池，注册了但关闭/健康检查看不到；合并为单一池（`register_mcp_tools_async` 调 `adopt(session_info)`）。 
- **`mcp_bridge` wrapper 工厂合并**：`_make_tool_wrapper` / `_make_resource_wrapper` 合成 `_make_session_wrapper(server_path, kind, name)`，减少重复样板。
- **`cli.py` --demo UTF-8 兜底**：Windows GBK 控制台打 `✓` 字符崩；`main()` 开头 stdout reconfigure 为 UTF-8。改用 `@template_agent` 替换已弃用的 `@register_agent` 装饰器形态。
- **`persistence.py` logger 切换**：自动保存失败告警从 `logging.getLogger(...)` 切到全库统一 loguru logger。
- **`agent_tool.check_permission` 参数命名**：`agent_name` → `agent_id`（实际传 uuid，与函数行为一致）。
- **`AnthropicAgent.conversation_with_tool(stream=False)` 丢字（v0.3.0 引入，v0.3.1 修，1.0.0 再次验证无回归）**：non-stream 分支在 `if llm_rsp.text:` 里同步 `assistant_blocks.append({"type": "text", ...})`。
- **`BaseAgent.conversation_with_tool` 多轮工具调用吞最终回复（v0.3.1 修）**：FC 模式 `tool=True` 递归末返回 `full_content` 而非 `work_history[-1]`。

### Deprecated
- **`Agent_Base_.Agent` / `anthropic_agent.AnthropicAgent`**：从这些路径 import 的旧代码 import 时打 `DeprecationWarning`，引导用户迁到 `from tangyuanAI import BaseAgent / AnthropicAgent`。
- **`DumplingsError` / `DumplingsConnectionError` / `DumplingsTimeoutError`**：保留 alias 但 import 时打 `DeprecationWarning`，引导用 `TangyuanError`。

### Removed
- **`.dumplingsAI_sessions/` 持久化目录**：改名 `.tangyuanAI_sessions/`；`/TANGYUAN_PERSISTENCE_DIR` 默认值同步迁移。
- **`DUMPLINGS_PERSISTENCE*` 环境变量**：改名 `TANGYUAN_PERSISTENCE*`（旧名仍可识别，但建议迁移）。

### Tests
- **171 / 174 通过**（3 known non-regression：① pre-existing `test_event_bus.test_user_binds_out_directly_on_instance` mock SSE bug；② env `dotenv` 缺失导致 `test_placeholder.test_core_exports` 找 `register_mcp_tools` 时静默 import 失败；③ flaky `test_concurrent_conversations_on_same_agent_dont_cross_contaminate` mock queue race）。
- **CI 矩阵**：GitHub Actions 跑 ruff + pytest on Python 3.10 / 3.11 / 3.12 × ubuntu / macos / windows = 9 个 job 全绿。

---

[Unreleased]: https://github.com/secret-tangyuan/tangyuanAI/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/secret-tangyuan/tangyuanAI/releases/tag/v1.0.0
[0.2.2]: https://github.com/secret-tangyuan/tangyuanAI/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/secret-tangyuan/tangyuanAI/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/secret-tangyuan/tangyuanAI/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/secret-tangyuan/tangyuanAI/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/secret-tangyuan/tangyuanAI/releases/tag/v0.1.0

### Fixed
- **`AnthropicAgent.conversation_with_tool(stream=False)` 丢字**
  - v0.3.0 bug：non-stream 模式下 LLM 返回的文本只累积到 `full_text`，但没进 `assistant_blocks`，
    最终 `return "".join(b.get("text", "") for b in last if b.get("type") == "text")` 永远空串
  - 修复：non-stream 分支在 `if llm_rsp.text:` 里同步 `assistant_blocks.append({"type": "text", "text": llm_rsp.text})`
  - 异步版 `aconversation_with_tool` 同样修复
- **`BaseAgent.conversation_with_tool` 同步多轮工具调用吞掉 LLM 最终回复**
  - v0.3.0 bug：tool=True 递归到末尾时 `if tool: return work_history[-1].get("content")` 把上轮 tool_result 当最终答案
  - 修复：递归到末尾应返回当前轮 LLM 的 `full_content`（FC 模式递归场景下 LLM 已经回过 LLM 那一句才是答案）

### Added
- **`AnthropicAgent` 补齐 4 个模板管理 builtin_tool**（v0.3.0 仅 `BaseAgent` 暴露，v0.3.1 补齐 `AnthropicAgent`）
  - `list_templates(name="")` / `activate_template(name)` / `deactivate_template(name)` / `register_template(name, description="")`
  - 与 BaseAgent 完全对称 —— 两协议公开 API 集合一致
- **`AnthropicAgent` 新增 `pack` 方法**（与 `BaseAgent.pack` 同款）
  - 把事件打包成带 `ai_uuid` / `ai_name` / `task_id` / `timestamp` 的 content dict 再调 `out`
  - 同步 / 异步两个 `conversation_with_tool` 内部从 `self.out({...})` 全部切到 `self.pack(...)`
  - 想接管输出行为请覆写 `out`，不要覆写 `pack`（与 BaseAgent 同样的约定）
- **`AnthropicAgent` 新增 `get_all_available_tools` 方法**（与 `BaseAgent` 同款）

### Changed
- **`BaseAgent` / `AnthropicAgent` 公开方法补全类型注解**
  - `out(content: dict) -> None` / `pack(...) -> None` / `conversation_with_tool(messages, tool: bool, images)`
  - `_generate_task_id() -> str` / `_get_timestamp() -> int`

### Tests
- **新增 `tests/_llm_mock.py`（共享 mock 基础设施）** 同时支持 OpenAI Chat Completions 与 Anthropic Messages API
  - 非流式 JSON / 流式 SSE 自动分派（按请求 body `stream` 字段）
  - 响应队列 + 请求日志：可断言"调了几次 / 每次发了什么"
  - `_connectivity` 探测请求短路（不消耗队列）
- **新增 `tests/test_anthropic_agent.py`（17 项）**
  - 覆盖 non-stream bug 修复（纯文本 / text+tool_use 混响 / 纯 tool_use）
  - 覆盖 stream 回归（纯文本 / text+tool_use 混响）
  - async 路径完整覆盖
  - 公开 API 对齐：pack / get_all_available_tools / 4 个模板管理 builtin_tool
- **新增 `tests/test_base_agent_parity.py`（6 项）**
  - 验证 BaseAgent 同样跑通 mock（非流式 + 流式 + 工具调用）
  - 验证 BaseAgent 的 4 个模板管理 builtin_tool
  - 验证 BaseAgent 与 AnthropicAgent 公开 API 集合一致
- **完整 `pytest tests/` 套件 97/97 通过，无回归**（74 旧 + 23 新）

## [0.3.0] - 2026-07-28

### Added
- **Agent 模板池（`agent_template_pool`）**
  - 新的"模板池"概念：用户注册的 Agent 类**只入池、不实例化、不写入 `agent_list`**
  - 与旧版 `@register_agent`（装饰时立刻实例化 + 写入 `agent_list`）的语义彻底分开
  - 模板的实例化时机由 `activate_template(name)` 显式控制
  - API：
    - `register_template(cls, name, uuid, description, overwrite)` —— 函数式入池
    - `@template_agent(name, uuid, description, overwrite)` —— 装饰器式入池（仅入池，不实例化）
    - `activate_template(name)` —— 把池中 `cls` 实例化并按 `uuid`+`name` 双键写入 `agent_list`
    - `deactivate_template(name)` —— 从 `agent_list` 移除实例，模板仍保留在池中
    - `remove_template(name)` —— 彻底从池中删除（连带从 `agent_list` 移除）
    - `list_templates()` / `get_template(name)` / `is_active(name)` —— 查询
- **`BaseAgent` 新增 4 个 builtin_tool**（让 LLM 在对话中自助管理模板池）
  - `list_templates(name="")` —— 列出/查询模板池
  - `activate_template(name)` —— 显式激活指定模板
  - `deactivate_template(name)` —— 反激活指定模板
  - `register_template(name, description="")` —— 占位说明，提示 LLM "注册 cls 必须在 Python 代码侧完成"
  - 与 `ask_for_help` / `list_agents` / `attempt_completion` / `reload` 一致走 `@builtin_tool` 装饰器，schema 自动从签名推导

### Changed
- **`@register_agent` 标记为弃用**
  - 仍然可用（向后兼容），但调用时通过库内 `logger.warning(...)` 输出迁移提示
  - 推荐迁移路径：`@template_agent(name)` + `activate_template(name)`

### Fixed
- **`Agent_list._ensure_meta` 缺省 `uuid` 不生效** —— 改为 `if not tpl.get("uuid"): tpl["uuid"] = tpl["name"]`，确保从类入参时也能正确补全
- **`BaseAgent.list_templates` 闭包漏 import `agent_list`** —— `NameError`，已在方法体内 `from .Agent_list import agent_list, ...`

### Tests
- **新增 `tests/test_template_pool.py`（33 项）** 覆盖完整模板池 API、装饰器、BaseAgent 4 个 builtin_tool
- 完整 `pytest tests/` 套件 74/74 通过，无回归

## [0.2.2] - 2026-07-21

### Added
- **`tangyuanAI.Agent` 协议无关的工厂基类**
  - 通过类属性 `protocol = "openai" | "anthropic"` 自动选择真实基类
  - 由 `_ProtocolMeta` metaclass 在类创建时替换占位基类，运行时零开销
  - 直接继承 `BaseAgent` / `AnthropicAgent` 的旧写法完全兼容
- **`examples/example7_unified_agent.py`**：演示 3 种写法
  （旧写法 / `Agent` + `protocol` / 动态根据 env 决定协议）

### Changed
- **`AnthropicAgent.api_provider` 默认值去掉**（强制显式设置 endpoint）
  - `_endpoint()` 在 `api_provider` 缺失时抛 `ValueError` 给出明确提示
  - 避免"忘记设置 endpoint 误走到官方 Anthropic API"的隐性 bug
- **全部 `examples/*.py` 中硬编码的 `model_name` 改为 `os.getenv()`**
  - `os.getenv("OPENAI_MODEL")` / `os.getenv("ANTHROPIC_MODEL")`，无 fallback
  - 配套 docstring 同步（`__init__.py` / `anthropic_agent.py` / `llm_transport.py`）

### Fixed
- **`AnthropicAgent` 流式分支漏写 `tool_use` 块**（导致 400 "tool result's tool id not found"）
  - 流式 + 非流式 + 异步非流式 3 处分支都补上 `assistant_blocks.append({"type": "tool_use", ...})`
  - 影响：多 Agent `ask_for_help` 链路不再因 `tool_use_id` 失配而失败
- **`LLMEvent` 缺 `stop_reason` 字段**（导致 `TypeError: unexpected keyword argument 'stop_reason'`）
  - 给 `@dataclass` `LLMEvent` 加 `stop_reason: Optional[str] = None`

## [0.2.1] - 2026-07-20

### Fixed
- `Agent_Base_.py` 内部两处错误的绝对导入 `from Tangyuan import agent_list`
  → 改为 `from tangyuanAI import agent_list`（安装后能正常工作）
- `__init__.py` 的 `__version__` 不再硬编码，自动从 `pyproject.toml` 的
  `version` 字段读取（`importlib.metadata`），pyproject 改版本号后无需再
  手动同步 `__init__.py`

### Changed
- `pyproject.toml` 的 `license` 字段从已弃用的 `{ text = "..." }` 表单改为
  SPDX 表达式 `license = "Apache-2.0"`，并移除 deprecated 的
  `License :: OSI Approved :: Apache Software License` classifier
- `AnthropicAgent` 的 class docstring 补充"自定义服务商"小节：
  - 官方 API、第三方代理、完整 URL、OpenAI 兼容网关的 `/anthropic` 子路径、
    AWS Bedrock 等场景
  - 自定义 header（Bearer / 租户 ID）的覆盖方式
  - 完整示例见 `examples/example6_anthropic_custom_provider.py`
- `BaseAgent.__init_subclass__` 增加覆写提示：子类覆写 `pack()` 但未覆写
  `out()` 时给出 warning，引导用户改 `out()` 而非 `pack()`

### Added
- `examples/example6_anthropic_custom_provider.py`：AnthropicAgent 自定义服务商的 4 种用法
- `RELEASING.md`：发布流程文档（PyPI Trusted Publisher 登记、tag 推送、日常发版、并发保护、FAQ）
- `.github/workflows/python-publish.yml` 重写为 **tag 触发自动发布**：
  - `push tags: ['vX.Y.Z', 'vX.Y.ZrcN', 'vX.Y.Z.postN']` 自动 build + publish + 创建 GitHub Release
  - 保留 `workflow_dispatch`（默认 dry_run 不发 PyPI）用于本地验证打包
  - `concurrency` 防止同 tag 重复跑
  - 完整使用 Trusted Publishing（OIDC），无需 API token

## [0.2.0] - 2026-07-19

### Added
- **`http_utils.py`**：基于 httpx 的中央 HTTP 客户端
  - `HTTPClient`（同步）+ `AsyncHTTPClient`（异步）
  - 指数退避 retry（429 / 5xx / 网络错），可配 `max_retries`
  - `timeout` 可单次覆盖
  - 错误分类：抛 `errors.APIError` 子类（`RateLimitError` / `InternalServerError` / `TimeoutError` / `ConnectionError` ...）
- **`errors.py`**：异常类型体系，对齐官方 `openai-python` / `anthropic-sdk-python` 的错误模型
- **`llm_transport.py`**：LLM Transport 抽象层
  - `LLMTransport` 抽象 + `HttpxOpenAITransport` / `HttpxAnthropicTransport` 实现
  - `ChatRequest` / `LLMResponse` / `LLMEvent` / `ToolCall` / `UsageInfo` 中性数据类型
  - Agent 不再直写 HTTP / SSE 解析 / tool_call 抽取；以后换底层（aiohttp / OpenAI SDK）只动一个 transport
- **`tool_runner.py`**：工具执行的 ThreadPoolExecutor
  - `ToolRunner.submit()`：超时返回 `(None, task_id)`，让 LLM 看到 `task_id` 占位继续做别的
  - 自带 `get_status` / `wait` 收割
  - 取代旧版「熔断 N 轮」的长线任务支持
- **`agent_queue.py`**（v0.2 强化）：全局 `AgentQueue`（默认 2 worker，60s idle 退出）
  - `ask_for_help` 改走队列 + 循环检测 + 深度限制
  - 不再因递归栈过深炸出
- **Pydantic 结构化输出**（Phase 2）
  - `@builtin_tool` 新增 `params_model` 参数；自动 `model.model_json_schema()` + `model_validate(args)`
  - 校验失败把错误回灌给 LLM，让它重试
  - `Optional` / 默认值字段不进 `required`
- **异步支持**（Phase 3 起步）
  - `BaseAgent.aconversation_with_tool` / `AnthropicAgent.aconversation_with_tool`
  - 基于 `AsyncHTTPClient` + `transport.achat_stream`
  - `asyncio_mode = "auto"` 开启 pytest 自动识别
- **Token 计数**：新增 `tiktoken>=0.7` 依赖（`token_utils` 计划中的基础）
- **依赖迁移**：`requests` → `httpx`，新增 `pydantic>=2.6`
- **CI**：GH Actions 升级到 `astral-sh/setup-uv@v6`，3.10/3.11/3.12 全绿

### Changed
- `BaseAgent` / `AnthropicAgent.conversation_with_tool` 重构：去掉手写 `requests.post` + SSE 解析，改走 `transport.chat/achat`
- 删除 `max_tool_turns=16` 熔断；改为无熔断循环（长线任务由 `tool_runner` 异步后台支持）
- `tool_timeout: float = 60` + `tool_max_workers: int = 8` 类属性（Agent 自定义超时，默认 60s 兜底）
- `BaseAgent.Connectivity` 走 `HTTPClient`，错误统一抛 `errors.APIError`
- 删除 `AnthropicAgent._call_blocking` / `_call_stream` 死方法（旧 SSE 解析逻辑已搬到 transport）
- README 重写为 PyPI 友好版

### Fixed
- 旧版 GH Actions（pip + flake8 + 无测试）持续失败问题
- 子包名 `tangyuanai` → `tangyuanAI` 命名不一致（主仓同步更新）
- Pydantic 校验后 `model_dump()` 把默认值也填进去（避免签名里 `**kwargs` 漏 default 报 TypeError）

## [0.1.1] - 2026-07-19

### Added
- `@builtin_tool` 装饰器：内建工具 schema 自动从签名+类型注解+docstring 推导
- `tool_registry.collect_builtin_tools(instance)` 收集器
- `BaseAgent` / `AnthropicAgent` 4 个内建方法（`ask_for_help` / `list_agents` / `attempt_completion` / `reload`）改用 `@builtin_tool` 装饰
- `_builtin_promote_overrides`：子类覆盖 `__init_subclass__` 自动继承 schema
- GH Actions CI（ruff + pytest on 3.10/3.11/3.12）
- PyPI 发布 workflow + Trusted Publishing 配置
- `tests/test_placeholder.py`：包级冒烟测试

### Changed
- 删除硬编码 `builtin_tools` 字典 / `builtin_tools_schema` 列表
- 同步 Anthropic 协议 Agent 重构
- README 重写为 PyPI 友好格式

### Fixed
- 旧版 GH Actions 工作流（`pip + flake8 + 无测试`）持续失败问题
- 子包名 `tangyuanai` → `tangyuanAI` 命名不一致（主仓同步更新）

## [0.1.0] - 2025-11-24

### Added
- 初始版本：多 Agent 注册、`tool_registry`、XML/FC 双模式工具调用、MCP 桥接、Skill 集成
- `BaseAgent` 抽象基类
- CLI 入口 `main.py`

[Unreleased]: https://github.com/secret-tangyuan/tangyuanAI/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/secret-tangyuan/tangyuanAI/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/secret-tangyuan/tangyuanAI/compare/v0.2.2...v1.0.0
[0.2.2]: https://github.com/secret-tangyuan/tangyuanAI/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/secret-tangyuan/tangyuanAI/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/secret-tangyuan/tangyuanAI/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/secret-tangyuan/tangyuanAI/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/secret-tangyuan/tangyuanAI/releases/tag/v0.1.0