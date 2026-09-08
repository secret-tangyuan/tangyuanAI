---
slug: persistence
title: 持久化
order: 9
icon: SAVE_OUTLINED
---

# Agent 状态持久化

> v0.4.0+ 新增。可插拔后端架构 + 实时自动保存。

把 agent 的运行状态（history / class 属性 / hooks / 任务 ID）保存到持久存储，
下次启动时恢复，让对话"长在"硬盘上。

## 三种使用方式

### 1. 完全手动：显式 save / load

```python
import tangyuanAI

agent = tangyuanAI.agent_list["weather"]

# 保存
tangyuanAI.save_state(agent, "weather-session-2026-07-30")
# 或写字符串（不落盘）
state_str = tangyuanAI.export_state_string(agent)

# 加载
agent2 = tangyuanAI.load_state("weather-session-2026-07-30")
# 或从字符串
agent3 = tangyuanAI.load_state_string(state_str)
```

### 2. 半自动：import 时 env var 启用 + 默认 file 后端

```bash
# .env 或 shell
export TANGYUAN_PERSISTENCE=on
export TANGYUAN_PERSISTENCE_DIR=./sessions
```

```python
# 程序里什么都不用写
import tangyuanAI
# ... 之后的 agent.conversation(...) 每次返回都会自动保存到 ./sessions/{uuid}.tas
```

### 3. 编程配置：运行时改 backend / 关闭

```python
import tangyuanAI

# 切到 sqlite
tangyuanAI.configure(enabled=True, backend="sqlite", db_path="./sessions.db")
# 或指定不同目录
tangyuanAI.configure(base_dir="./my-sessions")
# 关闭
tangyuanAI.disable()
# 当前是否启用
print(tangyuanAI.is_enabled())  # True / False
```

## 环境变量（import 时自动读取）

| 变量 | 取值 | 默认 | 作用 |
|---|---|---|---|
| `TANGYUAN_PERSISTENCE` | `on` / `off` | `off` | 启用自动持久化 |
| `TANGYUAN_PERSISTENCE_BACKEND` | `file` / `sqlite` | `file` | 选后端 |
| `TANGYUAN_PERSISTENCE_DIR` | 路径 | `./.tangyuanAI_sessions` | file 后端目录 |
| `TANGYUAN_PERSISTENCE_DB` | 路径 | `./.tangyuanAI_sessions.db` | sqlite 后端数据库 |
| `TANGYUAN_PERSISTENCE_KEY` | `uuid` / `name` | `uuid` | 自动保存的 key 策略 |

## 文件格式（`.tas` —— tangyuanAI Agent State）

默认 file 后端每个 session 一个文件，扩展名 `.tas`。人类可读、git diff 友好、
可手编。INI 头 + JSONL 体：

```ini
# tangyuanAI Agent State File
# format: tangyuan-state/1.0
# ===== DO NOT EDIT UNLESS YOU KNOW WHAT YOU'RE DOING =====

[META]
format_version = 1
schema_version = 0.4.0           # 自动从 tangyuanAI.__version__ 读
agent_uuid = abc123...
agent_name = weather
protocol = openai
class = examples.api.agents_config:WeatherAgent
saved_at = 2026-07-31T10:30:00+08:00
message_count = 42

[CONFIG]
prompt = 你是一个天气助手...
api_provider = https://api.example.com/v1/chat/completions
api_key_env = API_KEY            # 不存明文！只存 env var 名，加载时 os.getenv 重新解析
model_name = qwen3.5-plus
max_tokens = 4096
stream = true
fc_model = true
tool_timeout = 60.0
tool_max_workers = 8

[STATE]
current_task_id = tid-abc123
hooks = ["examples.api.agents_config:audit_hook"]

[HISTORY]
{"role":"system","content":"..."}
{"role":"user","content":"hi"}
{"role":"assistant","content":"hello","tool_calls":[...]}
{"role":"tool","tool_call_id":"...","name":"echo","content":"echo:yo"}
...
```

`schema_version` 自动读 `tangyuanAI.__version__`，pyproject bump 后状态文件自动
带上新版本号，不需要手动同步。

`api_key_env` 字段**不存明文**——只存环境变量名，加载时用 `os.getenv()` 重新解析。
避免 `.tas` 文件泄漏 API key。

## 后端

### FileBackend（默认，成熟）

```python
from tangyuanAI.persistence import FileBackend
backend = FileBackend(base_dir="./sessions")
backend.save("key", state_dict)
state = backend.load("key")
backend.delete("key")
keys = backend.list_keys()  # 返回 .stem 列表
```

### SQLiteBackend（实验性）

```python
from tangyuanAI.persistence import SQLiteBackend
backend = SQLiteBackend(db_path="./sessions.db")
# API 同 FileBackend
```

存到 SQLite 单表 `sessions`：

```sql
CREATE TABLE sessions (
    key TEXT PRIMARY KEY,
    meta TEXT,        -- JSON
    config TEXT,      -- JSON
    state TEXT,       -- JSON
    history TEXT,     -- JSONL
    saved_at TEXT
);
```

> **实验性**：v0.4.0 初次实现，**未在大规模并发下压测**。生产前请充分测试。

### 自定义后端

实现 `PersistenceBackend` 协议即可接入任意存储（Redis / Postgres / S3 ...）：

```python
from tangyuanAI.persistence import PersistenceBackend, register_backend

class RedisBackend:
    name = "redis"

    def __init__(self, client):
        self.client = client

    def save(self, key, state):
        import json
        self.client.set(f"duas:{key}", json.dumps(state, ensure_ascii=False))

    def load(self, key):
        import json
        raw = self.client.get(f"duas:{key}")
        if raw is None:
            raise FileNotFoundError(key)
        return json.loads(raw)

    def delete(self, key):
        return bool(self.client.delete(f"duas:{key}"))

    def list_keys(self):
        return [k.decode().removeprefix("duas:") for k in self.client.keys("duas:*")]

register_backend("redis", RedisBackend(my_redis_client), set_as_default=True)
```

## 类身份解析

保存时记 `class` 全限定路径（`module:qualname`）。加载时：

1. **首选**：`importlib` 按路径 import 重建类
2. **降级 1**：查 `agent_list[uuid]`（必须先 `activate_template`）
3. **失败**：抛 `AgentNotFoundError`（带清晰错误信息 + 修复建议）

```python
# 加载时如果原类已删除，但 agent_list 里有同 uuid 的实例
import tangyuanAI
tangyuanAI.activate_template("my_agent")  # 把类放回 agent_list
agent = tangyuanAI.load_state("my-session")  # 走降级 1 路径
```

## hooks 持久化

`tool_call_hooks` 存函数全限定名，加载时尝试 `importlib` 重新绑定。找不到的 hook
静默跳过（warning）：

```python
def my_hook(event_type, tool_name, ...):
    ...

agent.register_tool_hook(my_hook)
tangyuanAI.save_state(agent, "k1")  # hooks = ["my.module:my_hook"]
# 加载时如果 my_hook 还能 import，自动 re-bind；不能就跳过
```

## 实时保存（自动）

`@_auto_save` / `@_auto_save_async` 装饰器包了 `BaseAgent` / `AnthropicAgent` 的
`conversation` / `aconversation`。最外层调用退出时自动保存
一次，递归调用（如 FC 模式的多轮工具调用）不重复保存——通过 `_conv_depth` 计数
器保证。

```python
import os
os.environ["TANGYUAN_PERSISTENCE"] = "on"
os.environ["TANGYUAN_PERSISTENCE_DIR"] = "./sessions"

import tangyuanAI
# 之后所有 agent 的 conversation 都会自动写到 ./sessions/{uuid}.tas
```

手动触发（不开 enable 也行）：

```python
from tangyuanAI.persistence import auto_save
auto_save(agent)  # 用 agent.uuid 作 key（默认），写到默认 backend
```

## API 速查

### 顶层函数

| 函数 | 作用 |
|---|---|
| `save_state(agent, key, *, backend=None)` | 显式保存 |
| `load_state(key, *, backend=None) -> Agent` | 显式加载 |
| `delete_state(key, *, backend=None) -> bool` | 显式删除 |
| `list_states(*, backend=None) -> list[str]` | 列出所有 key |
| `export_state_string(agent) -> str` | agent → 字符串（不落盘） |
| `load_state_string(s) -> Agent` | 字符串 → agent |
| `configure(*, enabled, backend, base_dir, db_path, key_strategy)` | 编程配置 |
| `is_enabled() -> bool` | 自动持久化是否启用 |
| `disable()` | 关闭 |
| `auto_save(agent) -> bool` | 手动触发一次（不影响 enable 状态） |
| `register_backend(name, backend, set_as_default=False)` | 注册自定义后端 |
| `set_default_backend(name)` | 切换默认后端 |

### Agent 方法

```python
agent.save_state(key, backend=None)   # 调 save_state(self, ...)
Agent.load_state(key, backend=None)   # classmethod；调 load_state(...)
```

### 异常

| 异常 | 何时抛 |
|---|---|
| `AgentNotFoundError` | 类路径解析失败 + agent_list 也没有 |
| `FormatError` | 状态文件格式版本不识别 |

## 完整单测

`tests/test_persistence.py`（36 项）覆盖：

- 导出格式 / 多行转义
- FileBackend：roundtrip / delete / list / 路径穿越保护
- SQLiteBackend：roundtrip / delete / list
- 插件注册 / 重复注册 / 未知 backend
- 类身份解析：成功 / 降级到 agent_list / 失败抛错
- 自动保存：默认关闭 / configure 启用 / env var 启用
- 装饰器：conversation 退出时保存 / async / 递归不重复保存
- key_strategy 切换 / 持久化失败不阻塞对话
- INI parser 边界
- schema_version 自动从 `tangyuanAI.__version__` 读

## 边界 / 已知限制

1. **tool_call_hooks 找不到**：warning 跳过，不阻断。
2. **类路径找不到 + agent_list 没有**：抛 `AgentNotFoundError`，用户必须修复。
3. **子类自定义 `__init__`** 不会被持久化重放（持久化只重放 `__init__` 之后的状态）。
   加载时只调用 `cls()`（标准 `__init__`）。
4. **跨进程**：tool_call_hooks、tool_registry、agent_list 都是进程内状态。加载
   时如果 `agent_list` 已有同名 agent，行为由 `check_permission` 决定。
5. **history 很大**：JSONL 按行解析。如果 history 几万条，文件会很大。
   v0.4.0 不做 gzip 透明压缩（.tas.gz），未来考虑。
6. **SQLite 并发**：v0.4.0 初次实现，**未压测**。生产前请充分测试。