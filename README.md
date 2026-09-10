# tangyuanAI

> 一个轻量、模块化的多智能体协作框架，让 LLM 像"公司团队"一样分工完成任务。
>
> A lightweight, modular multi-agent collaboration framework — let LLMs work as a "company team" to get things done.

[![PyPI](https://img.shields.io/pypi/v/tangyuanAI.svg)](https://pypi.org/project/tangyuanAI/)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![CI](https://github.com/secret-tangyuan/tangyuanAI/actions/workflows/python-package.yml/badge.svg)](https://github.com/secret-tangyuan/tangyuanAI/actions)

**作者 / Author**：[secret-tangyuan](https://github.com/secret-tangyuan) · [个人介绍 / Gravatar](https://gravatar.com/secrettangyuan)
**文档站 / Docs**：[ai.secret-tangyuan.com/docs](https://ai.secret-tangyuan.com/docs)

---

## 这个项目解决的问题 / The problem this exists to solve

每家 LLM 都有自己的协议方言。每家都不一样。
Every LLM provider speaks its own dialect. Every one is different.

OpenAI 要 `messages[].role=tool` 块；Anthropic 要 `tool_result` 内容块加 `tool_use_id` 回声；OpenAI 新的 Responses API（`/v1/responses`）要一个 `input` 列表装 typed items；你们公司机房里的网关又不一样。
OpenAI wants `messages[].role=tool` blocks; Anthropic wants a `tool_result` content block with a `tool_use_id` echo; OpenAI's newer Responses API (`/v1/responses`) wants an `input` list of typed items; the gateway in your company's basement wants something else entirely.

如果你写 `response = openai.ChatCompletion.create(...)`，你已经把自己锁死在一个 provider。
If your agent code says `response = openai.ChatCompletion.create(...)`, you've already locked yourself to one provider.

想对比 Claude vs Qwen？要 `pip install` 另一个 SDK，然后重写循环。
Want to compare Claude vs Qwen? `pip install` another SDK and rewrite the loop.

想用代理绕 rate limit？要改三个 URL。
Want to reroute through a regional proxy to dodge rate limits? Patch the URL in three places.

想切到 Responses 因为它有内置 web search？要丢你的 streaming 解析。
Want to swap to Responses because it has built-in web search? Throw away your streaming parser.

**tangyuanAI 是一个薄层，把协议差异收拢到一个地方。**
**tangyuanAI is a thin layer that puts the protocol differences in one place.**

你的 Agent 类写一次。底层 transport 换不换协议都不影响你应用代码。
Your agent class stays the same. The transport underneath you can change without rewriting anything in your application code.

---

## tangyuanAI 帮你做 / What tangyuanAI does for you

一个 `tangyuanAI.Agent` 子类就是一个可调的 Python 对象。
A `tangyuanAI.Agent` subclass is a callable Python object.

给它一个 prompt、一组工具、一个端点，它就能找你指定的 LLM 跑对话。
You give it a prompt, a toolset, and an endpoint — it talks to whichever LLM you point it at.

切 provider 只需要改**一个**类字段：
Switching providers is changing a single class field:

```python
import tangyuanAI

@tangyuanAI.template_agent("writer", uuid="…", description="…")
class Writer(tangyuanAI.Agent):
    prompt       = "…"
    api_provider = os.getenv("API_BASE", "https://api.openai.com/v1")
    model_name   = os.getenv("MODEL",    "gpt-5")
    api_key      = os.getenv("API_KEY",  "")
    # protocol = "openai"  ← 默认，不用设
```

同一个类。把 `protocol = "anthropic"` 改一下，它就走 Anthropic Messages API 了。
Same class. Change `protocol = "anthropic"` and it now speaks Anthropic Messages API.

把 `protocol = "openai-responses"` 改一下，它就走 `/v1/responses` 了。
Change `protocol = "openai-responses"` and it speaks `/v1/responses`.

把 `api_provider` 改成你公司网关的地址，它就跟你公司网关对话——不管那个网关讲什么。
Change `api_provider` to a URL your company gateway returns and it speaks whatever your gateway returns.

Transport 层重写 wire format；Agent 不知道也不在乎。
The transport layer rewrites the wire format; the agent doesn't know or care.

支撑这一切有三块。它们都不算什么"feature bullet"——它们的存在全部源于同一个动机：别再因为底层 transport 动一下就重写 agent。
Three planks hold this up. None of them is a feature bullet — they're all consequences of wanting to stop rewriting agents when the transport moves:

1. **一个 Agent 类，一个 `protocol` 字段。**
   **One Agent class, one protocol field.**
   一个注册表把 protocol 字符串映射到 transport 实现。加一个新 provider 只需一个 transport 类 + 一次 `register_protocol(...)` 调用。Agent 和你的工具都不用改。
   A registry maps protocol strings to transport implementations. Adding a new provider is one transport class and one `register_protocol(...)` call. The Agent and your tools don't change.

2. **工具与协议无关。**
   **Tools are protocol-agnostic.**
   你写 `def get_weather(city: str) -> str:` 一次。不管 LLM 用原生 function-calling 还是 stream 里塞 XML，都给你桥接好了。ACL、Pydantic 校验、单调用超时都内置。
   You write `def get_weather(city: str) -> str:` once. Whether the LLM calls it via native function-calling or via XML blocks in the stream, the framework bridges it. ACL + Pydantic validation + per-call timeouts are wired in.

3. **多 Agent 就是 `ask_for_help` 一个调用。**
   **Multi-agent is just `ask_for_help`.**
   `agent_list` 上的 Agent 能互相调用，带循环检测 + 深度限制（worker pool 里），所以调度器扇出 50 个研究员 Agent 不会爆栈或卡死。
   Agents on the same `agent_list` can call each other, with cycle detection and depth limits wired into a worker pool — so a scheduler that fans out to 50 researcher agents won't blow your stack or hang on a cycle.

持久化（`.tas` 文件 + 可插拔后端）、MCP 桥接、Skill 发现、事件总线——这些都因为某些具体项目需要它们才存在。**它们不是买点**。
Persistence (`.tas` files, pluggable backends), MCP bridging, the Skill discovery format, the event bus — all of those exist because something concrete required them in a real project. **They're not the pitch.**

---

## 快速开始 / Quickstart

```bash
pip install tangyuanAI
export API_KEY="sk-…"                      # OpenAI 协议
export ANTHROPIC_API_KEY="sk-ant-…"        # Anthropic 协议
```


**KB 与图片生成（v1.1.0+）**：默认已包含在主包，开箱即用：

```bash
pip install tangyuanAI                       # 含完整 KB（RAG）+ 图片生成实现（vendored）
tangyuanai plugin status                     # 看 KB / Image 子系统状态（vendored vs 第三方）
```

要替换默认实现（第三方发布兼容包）：

```bash
# 方式 1：从 git URL 装（推荐，跨开发期都能用）
tangyuanai plugin install-git https://github.com/your-fork/tangyuanai-kb-alt.git

# 方式 2：标准 pip 装（包已发 PyPI）
pip install tangyuanai-kb-alt
```

第三方包通过 `tangyuanai.plugins` entry point 注册（type=`knowledge_base` / `image_generation`），
`tangyuanAI.kb` / `tangyuanAI.imaging` 自动优先用第三方，没装就走 vendored 默认。

接口文档（如何写兼容插件）：[docs/plugin-dev.md](docs/plugin-dev.md)。

```python
import os
import tangyuanAI
from tangyuanAI.Agent_list import activate_template

@tangyuanAI.tool_registry.register_tool(
    description="查询某城市天气（演示用返回假数据）",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
)
def get_weather(city: str) -> str:
    return f"{city}今天晴，温度 25°C"


@tangyuanAI.template_agent(
    "weather",
    uuid="weather-uuid-1",
    description="天气查询助手",
)
class WeatherAgent(tangyuanAI.Agent):                       # 协议无关的 Agent 工厂基类
    protocol    = "openai"                                  # 一行声明走哪个协议
    prompt      = "你是天气助手，用 get_weather 工具回答问题"
    api_provider = os.getenv("API_BASE", "https://api.openai.com/v1/chat/completions")
    model_name   = os.getenv("MODEL",    "gpt-5")
    api_key      = os.getenv("API_KEY")


if __name__ == "__main__":
    activate_template("weather")
    agent = tangyuanAI.agent_list["weather"]
    agent.conversation("北京今天天气怎么样？")
```

切协议只改一个字段 —— 而且只改一个字段：
Switching protocols means changing one field — and only one field:

```python
@tangyuanAI.template_agent("reviewer", uuid="reviewer-uuid-1",
                            description="走 Claude 协议的评审 Agent")
class ReviewerAgent(tangyuanAI.Agent):                 # 不再 import AnthropicAgent
    protocol     = "anthropic"                          # 一行切协议
    prompt       = "你是评审助手，用 attempt_completion 总结"
    api_provider = "https://api.anthropic.com"
    model_name   = "claude-3-5-sonnet-latest"
    api_key      = os.getenv("ANTHROPIC_API_KEY")

weather   = tangyuanAI.agent_list["weather"]
reviewer  = tangyuanAI.agent_list["reviewer"]
reviewer.conversation(f"刚才 {weather.name} 说北京 25°C 晴，请评审")
```

---

## 协议简单性 —— 1 行 = 100 行 / Protocol simplicity — 1 line = 100 lines

Agent 和 Agent 之间通信需要一套协议。Google 的 A2A 协议是个公开参考（JSON-RPC 2.0 over HTTP + SSE 流式任务 + agent card 发现 + 状态机：`submitted → working → input-required → completed/failed/canceled`）。

Agent-to-agent communication needs a protocol. Google's A2A protocol is one open reference: JSON-RPC 2.0 over HTTP, SSE-streamed tasks, agent card discovery, plus a state machine (`submitted → working → input-required → completed/failed/canceled`).

如果从零写一个 A2A 客户端调远端 Agent，你会写这样的代码：

If you wrote an A2A client from scratch to talk to a remote agent, it'd look like:

```python
import httpx, json, asyncio, uuid

REMOTE_AGENT_URL = "http://remote-agent.example.com"

# 1. 发现：通过 well-known 端点拉 agent card（skills、auth schemes、transport 偏好）
async def call_remote_agent(user_text: str) -> str:
    async with httpx.AsyncClient() as client:
        card = (await client.get(f"{REMOTE_AGENT_URL}/.well-known/agent.json")).json()
        # card 告诉你远端 agent 支持什么 skills、需要什么 auth

        # 2. 构造 JSON-RPC 2.0 + SendMessageRequest
        req = {
            "jsonrpc": "2.0", "id": 1,
            "method": "tasks/sendSubscribe",
            "params": {
                "id": str(uuid.uuid4()),
                "sessionId": "session-1",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": user_text}],
                },
                "acceptedOutputModes": ["text/plain"],
            },
        }

        # 3. SSE 流订阅 + 状态机分支
        final_state, final_text = None, ""
        async with client.stream(
            "POST", f"{REMOTE_AGENT_URL}/a2a/v1/tasks/sendSubscribe",
            json=req,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "X-A2A-Headers": json.dumps({"X-Locale": "zh-CN"}),
            },
        ) as r:
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                if "status" in event:
                    state = event["status"]["state"]
                    if state == "input-required":
                        # 用户侧弹窗补信息 → SendMessage 续推
                        ...
                    elif state in ("completed", "failed", "canceled"):
                        final_state = state
                if "artifact" in event:
                    for part in event["artifact"].get("parts", []):
                        if part.get("type") == "text":
                            final_text += part["text"]
                if final_state:
                    break
        return final_text if final_state == "completed" else ""

# 4. 错误处理：远端 agent 抛 SkillNotFound / ToolError / 网络中断 / SSE 断流
#    —— 自己写重试 + 状态恢复 + 重连。
```

> 50+ 行：发现 + JSON-RPC 构造 + SSE 流解析 + 状态机分支 + 鉴权头 + 错误重试 + 重连。
> 50+ lines: discovery + JSON-RPC construction + SSE stream parsing + state-machine branching + auth headers + error retry + reconnection.

用 tangyuanAI 写——同样的"请调一下 writer_agent 来帮我查北京天气"——只一行：

Writing the same "ask writer_agent to look up Beijing weather" in tangyuanAI — one line:

```python
result = tangyuanAI.agent_list["scheduling_agent"].ask_for_help(
    agent_id="writer_agent",
    message="请帮我查一下北京今天天气",
)
# .ask_for_help 里自动：cycle detection / depth limit / worker pool / XML↔FC 桥接 / 流式 assemble
```

> 一个调用：循环检测、深度限制、worker 池、协议兼容（XML/FC）、流式装配都内建。
> One call: cycle detection, depth limiting, worker pool, protocol bridging (XML/FC), stream assembly — all built in.

Agent 的 `prompt` 里只要写"你可以用 `<ask_for_help>` 请其他 Agent"——LLM 自己知道怎么调。这是协议描述（人类可读）+ 工具描述（机器可执行）合并的好处。

The agent's `prompt` only has to say "you may use `<ask_for_help>` to call other agents" — the LLM figures out how to call it. That's the win from having protocol descriptions (human-readable) and tool descriptions (machine-callable) merged into the same surface.

而且工具的 `schema` 也省了 —— **不用写 function 的 schema**：
And tool `schema` is also skipped — **no need to write the function schema**:

传统 `/definitions/...` JSON Schema：Traditional `/definitions/...` JSON Schema:

```python
# A2A skill 注册：手写整套 JSON Schema
skill_def = {
    "name": "search_web",
    "description": "搜索互联网信息",
    "inputSchema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
                "minLength": 1,
                "maxLength": 200,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}
agent_card["skills"].append(skill_def)   # 远端 agent 据此发现我能做什么
```

tangyuanAI：用 Python 函数签名 + 类型注解，schema 自动推：
tangyuanAI: Python signature + type annotations, schema auto-derived:

```python
from tangyuanAI import builtin_tool

@builtin_tool(
    description="搜索互联网信息",
    params={"query": "搜索关键词"},   # 描述可在此覆写；类型从签名推
)
def search_web(query: str) -> str:        # type=string / required=query 都是从签名推
    return "搜索结果..."
```

> 一个 Python 函数 = 一份 JSON Schema。无需重复声明字段名 / 类型 / required / 描述。
> One Python function = one JSON Schema. No need to repeat field names / types / required / descriptions.

---

## 一张架构图 / Architecture in one diagram

```
                ┌─────────────────────────────────────────────┐
                │  your application (tangyuanAI.agent_list)  │
                └───────────────┬─────────────────────────────┘
                                │
                ┌───────────────▼───────────────────────┐
                │  Agent (protocol = "openai" | "anthropic"│  ← 你写一份的代码
                │             | "openai-responses")        │     / The code you write once
                │  — prompt / tools / hooks / memory     │
                └───────────────┬───────────────────────┘
                                │ conversation(...)
                                │
                ┌───────────────▼───────────────────────┐
                │  LLMTransport (协议差异封装)           │  ← 框架提供
                │                                       │     / Provided by the framework
                │  - HttpxOpenAITransport                │
                │  - HttpxAnthropicTransport              │
                │  - HttpxOpenAIResponsesTransport         │
                │  - 自家网关 = register_protocol(...)    │
                └───────────────┬───────────────────────┘
                                │
                            HTTPS / SSE
                                │
                ┌───────────────▼───────────────────────┐
                │  OpenAI Chat Completions /              │
                │  OpenAI Responses /                     │
                │  Anthropic Messages /                   │
                │  你的网关 / 你明天的网关               │
                └─────────────────────────────────────────┘
```

**你写 Agent。** 协议在 transport 后面变。
**You touch the Agent.** Protocols change behind the transport.

工具跨协议复用（同一个定义、同一个 ACL）。多 Agent 路由就是 prompt 里 `ask_for_help` 一行调用——不用学额外的 orchestrator 类。
Tools are reusable across protocols (same definition, same ACL). Multi-agent routing is a one-line `ask_for_help` call inside any agent's prompt — no separate orchestrator class to learn.

---

## 怎么写好 Agent —— 4 件事 / How to write good Agents (the 4 things to internalize)

1. **一个 `template_agent` + 一个 `activate_template`。**
   **One `template_agent` + one `activate_template`.**
   装饰器只注册；激活才实例化。这让你可以在 `examples/agents_config.py` 里写注册表，import 时不用付实例化成本，直到真用到。
   Decoration only registers; activation instantiates. This is what lets you write the registry in `examples/agents_config.py` and have it imported without paying instantiation cost until you actually need it.

2. **`@template_agent(..., description="…")` 是一句话，不是段。**
   **`@template_agent(..., description="…")` is a sentence, not a paragraph.**
   Agent 在 `tangyuanAI.list_agents()` 里可发现，并通过 `list_agents` 内建工具展示给别的 Agent。description 是别的 Agent 决定"要不要调我"时读的。
   Agents are discoverable in `tangyuanAI.list_agents()` and shown back to other agents via `list_agents` builtin. The description is what they read to decide whether to call you.

3. **工具描述决定工具选择。**
   **Tool descriptions drive tool selection.**
   你写的 schema 和 docstring 直接决定 LLM 调的是 `get_user_orders(user_id=...)` 还是 `list_all_orders()`。在这上面花时间。
   The schema and docstring you write determine whether the LLM calls `get_user_orders(user_id=...)` or `list_all_orders()`. Spend the time on descriptions.

4. **自定义 `out()` 是接入点。**
   **Custom `out()` is the integration point.**
   默认打印文本；覆写可以把事件推到 logger、队列、UI。别动 `pack()`。
   Default prints text; override to push events into a logger, a queue, a UI. Don't override `pack()`.

这些之外，看更深的内容：
Beyond these four, read the deeper docs:

- **[文档站 / Documentation](https://ai.secret-tangyuan.com/docs)** — 完整 API、钩子、ACL、MCP、持久化、Skill，全在这。*(YAML-frontmatter 驱动的 `docs/*.md`；push 自动部署。)*
  *(YAML-frontmatter-driven `docs/*.md`; push auto-deploys.)*
- **[CHANGELOG.md](./CHANGELOG.md)** — 每个版本的 Added / Fixed / Changed 记录。*(这个文件总在变；README 长期稳定。)*
  *(This file changes; the README stays stable.)*

---

## 开发与测试 / Development & testing

```bash
git clone https://github.com/secret-tangyuan/tangyuanAI.git
cd AI_Company
uv sync --group dev
uv run pytest tangyuanAI/tests/ -v
uv run ruff check tangyuanAI/
```

`tangyuanAI/tests/_llm_mock.py` 提供的 mock 让 Agent 测试构造完整 wire-format payload，断言发送和接收——无需 API key。
The mock layer in `tangyuanAI/tests/_llm_mock.py` lets Agent tests construct full wire-format payloads and assert on what got sent and what came back — no API keys required.

---

## 贡献 / Contributing

开 PR。push 前跑：
Open a PR. Before pushing, run:

```bash
uv run ruff check .
uv run pytest
```

加新 transport（新 provider 或网关）？实现 `LLMTransport` 并在 `__init__.py` 调 `register_protocol(name, cls)`。框架处理剩下所有。
For new transports (a new provider or gateway), implement `LLMTransport` and call `register_protocol(name, cls)` in your package's `__init__.py`. The framework handles the rest.

---

## 许可证 / License

Apache License 2.0

Copyright 2025-2026 [Secret Tangyuan](https://github.com/secret-tangyuan)

```
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```