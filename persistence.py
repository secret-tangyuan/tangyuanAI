# -*- coding: utf-8 -*-
"""
Agent 状态持久化 —— 可插拔后端架构。

设计目标：

1. **可读 / 可 diff / 可手编**：默认 ``FileBackend`` 用 INI 头 + JSONL 体的
   自定义格式（扩展名 ``.tas``，v0.4.0–v0.4.x 旧版用 ``.duas``，v1.0.0 起仍可读），高级用户可直接 ``cat`` 看 / ``git diff`` 跟 /
   手动改 ``[CONFIG]`` 切模型。
2. **可插拔后端**：通过 :class:`PersistenceBackend` 协议接入任意存储
   （SQLite / Redis / Postgres / S3 ...）。框架内置 :class:`FileBackend`（默认）
   和 :class:`SQLiteBackend`（**实验性**）。
3. **类身份可重建**：保存时记录类全限定路径（``module:qualname``），加载时
   按路径 ``importlib`` 重绑；失败时查 ``agent_list[uuid]``；再失败抛清晰错误。

持久化的状态：

- ``[META]``：format_version / schema_version / agent_uuid / agent_name /
  protocol / class / saved_at / created_at
- ``[CONFIG]``：prompt / api_provider / api_key_env（**不存明文**）/ model_name /
  max_tokens / stream / fc_model / tool_timeout / tool_max_workers 等类属性
- ``[STATE]``：current_task_id / hooks（``module:qualname`` 列表）
- ``[HISTORY]``：line-delimited JSON，每行一条消息（多模态 base64 内嵌）

插件注册::

    from tangyuanAI.persistence import register_backend, FileBackend, SQLiteBackend

    register_backend("file", FileBackend(), set_as_default=True)
    register_backend("sqlite", SQLiteBackend("sessions.db"), set_as_default=False)

    # 顶层 API
    import tangyuanAI
    tangyuanAI.save_state(agent, "weather-session", backend="sqlite")
    agent2 = tangyuanAI.load_state("weather-session", backend="sqlite")
"""
from __future__ import annotations

import datetime
import functools
import importlib
import json
import os
import sqlite3
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

FORMAT_NAME = "tangyuan-state"
FORMAT_VERSION = 1
# 状态文件扩展名：v1.0.0 起用 .tas（T-Agent-State）；旧 .duas（基于 dumplingsAI 缩写）仍识别。
CURRENT_EXT = ".tas"
LEGACY_EXT = ".duas"
# schema_version 不硬编码 —— export 时从 tangyuanAI.__version__ 自动读取，
# 保证 pyproject.toml bump 后状态文件自动带上新版本号。fallback 用 "0.0.0+unknown"。
SCHEMA_VERSION_FALLBACK = "0.0.0+unknown"

from .logging_config import logger  # noqa: E402  (与 FileBackend 段一起使用)


def _get_schema_version() -> str:
    """读 tangyuanAI.__version__；持久化模块被 import 时 tangyuanAI.__init__ 还没跑完，
    所以必须延迟 import（在函数内 import）避免循环依赖。"""
    try:
        import tangyuanAI  # noqa: PLC0415 - 延迟 import 防循环
        v = getattr(tangyuanAI, "__version__", None)
        if v:
            return v
    except (ImportError, AttributeError):
        pass
    return SCHEMA_VERSION_FALLBACK

__all__ = [
    "PersistenceBackend",
    "FileBackend",
    "SQLiteBackend",
    "backends",
    "register_backend",
    "get_backend",
    "set_default_backend",
    "configure",
    "is_enabled",
    "disable",
    "auto_save",
    "save_state",
    "load_state",
    "delete_state",
    "list_states",
    "export_state_string",
    "parse_state_string",
    "load_state_string",
    "AgentNotFoundError",
    "FormatError",
]


# ============================================================================
# Exceptions
# ============================================================================

class AgentNotFoundError(LookupError):
    """类路径解析失败 + agent_list 也没有 + 没有 [CONFIG] 备份时抛出。"""


class FormatError(ValueError):
    """状态文件格式不识别 / 版本不兼容。"""


# ============================================================================
# Backend protocol
# ============================================================================

class PersistenceBackend(Protocol):
    """持久化后端协议。

    后端只需实现 4 个方法，状态以 ``Dict[str, Any]`` 形式传递。
    ``key`` 是用户给定的标识符（文件名 / 表主键 / Redis key ...）。
    """

    name: str

    def save(self, key: str, state: Dict[str, Any]) -> None: ...
    def load(self, key: str) -> Dict[str, Any]: ...
    def delete(self, key: str) -> bool: ...
    def list_keys(self) -> List[str]: ...


# ============================================================================
# Backend registry
# ============================================================================

@dataclass
class _Registry:
    backends: Dict[str, PersistenceBackend] = field(default_factory=dict)
    default_name: Optional[str] = None
    enabled: bool = False
    key_strategy: str = "uuid"  # "uuid" | "name"

    def register(self, name: str, backend: PersistenceBackend, set_as_default: bool = False) -> None:
        if name in self.backends:
            raise ValueError(f"backend {name!r} already registered")
        self.backends[name] = backend
        if set_as_default or self.default_name is None:
            self.default_name = name

    def get(self, name: Optional[str] = None) -> PersistenceBackend:
        if name is None:
            if self.default_name is None:
                raise RuntimeError("no default persistence backend registered")
            name = self.default_name
        if name not in self.backends:
            raise KeyError(
                f"backend {name!r} not registered; "
                f"available: {sorted(self.backends)}"
            )
        return self.backends[name]


backends = _Registry()


def register_backend(name: str, backend: PersistenceBackend, set_as_default: bool = False) -> None:
    backends.register(name, backend, set_as_default=set_as_default)


def get_backend(name: Optional[str] = None) -> PersistenceBackend:
    return backends.get(name)


def set_default_backend(name: str) -> None:
    if name not in backends.backends:
        raise KeyError(f"backend {name!r} not registered")
    backends.default_name = name


# ============================================================================
# Auto-persistence configuration（v0.3.2+ 实时存储）
# ============================================================================

def configure(
    *,
    enabled: Optional[bool] = None,
    backend: Optional[str] = None,
    base_dir: Optional[str] = None,
    db_path: Optional[str] = None,
    key_strategy: Optional[str] = None,
) -> None:
    """配置全局自动持久化。

    在程序启动早期（import tangyuanAI 之后、第一次 conversation 之前）调用一次，
    之后所有 agent 的 ``conversation`` / ``aconversation`` 调用都会在返回时自动保存当前状态
    （旧名 ``conversation_with_tool`` / ``aconversation_with_tool`` 作为 deprecated alias 同样适用）。

    Args:
        enabled: True 启用自动保存；False 关闭；None 表示不动
        backend: 后端名称（"file" / "sqlite" / 自定义注册过的）
        base_dir: file 后端的目录（仅在 backend="file" 时生效）
        db_path: sqlite 后端的数据库文件路径（仅在 backend="sqlite" 时生效）
        key_strategy: 自动保存的 key 策略

            - ``"uuid"``（默认）：用 ``agent.uuid`` 作 key，每个 agent 一份"当前状态"
            - ``"name"``：用 ``agent.name`` 作 key

    环境变量等价（import 时自动读取）：

    - ``TANGYUAN_PERSISTENCE=on|off``  → 启用/关闭
    - ``TANGYUAN_PERSISTENCE_BACKEND=file|sqlite``
    - ``TANGYUAN_PERSISTENCE_DIR=./sessions`` （file 后端）
    - ``TANGYUAN_PERSISTENCE_DB=./sessions.db`` （sqlite 后端）
    - ``TANGYUAN_PERSISTENCE_KEY=uuid|name``
    """
    if enabled is not None:
        backends.enabled = bool(enabled)
    if backend is not None:
        if backend not in backends.backends:
            raise KeyError(
                f"backend {backend!r} not registered; "
                f"available: {sorted(backends.backends)}"
            )
        backends.default_name = backend
    if base_dir is not None and "file" in backends.backends:
        # 重建 file 后端指向新目录
        backends.backends["file"] = FileBackend(base_dir=base_dir)
    if db_path is not None and "sqlite" in backends.backends:
        backends.backends["sqlite"] = SQLiteBackend(db_path=db_path)
    if key_strategy is not None:
        if key_strategy not in {"uuid", "name"}:
            raise ValueError(f"key_strategy must be 'uuid' or 'name', got {key_strategy!r}")
        backends.key_strategy = key_strategy


def is_enabled() -> bool:
    """当前是否启用了自动持久化。"""
    return bool(backends.enabled)


def disable() -> None:
    """关闭自动持久化（不影响已注册的 backend 和显式 save_state 调用）。"""
    backends.enabled = False


def _read_env_config() -> None:
    """在 tangyuanAI/__init__.py 顶部调用，读取环境变量。"""
    flag = os.environ.get("TANGYUAN_PERSISTENCE", "").strip().lower()
    if flag not in {"on", "true", "1", "yes"}:
        return

    backend_name = os.environ.get("TANGYUAN_PERSISTENCE_BACKEND", "").strip().lower() or "file"
    base_dir = os.environ.get("TANGYUAN_PERSISTENCE_DIR", "./.tangyuanAI_sessions")
    db_path = os.environ.get("TANGYUAN_PERSISTENCE_DB", "./.tangyuanAI_sessions.db")
    key_strategy = os.environ.get("TANGYUAN_PERSISTENCE_KEY", "uuid").strip().lower()

    # 应用到已注册的 backend 上
    if backend_name in backends.backends:
        if backend_name == "file":
            backends.backends["file"] = FileBackend(base_dir=base_dir)
        elif backend_name == "sqlite":
            backends.backends["sqlite"] = SQLiteBackend(db_path=db_path)
        backends.default_name = backend_name
    if key_strategy in {"uuid", "name"}:
        backends.key_strategy = key_strategy
    backends.enabled = True


def auto_save(agent: Any) -> bool:
    """``conversation`` / ``aconversation`` 退出时自动调用（v1.3.0 之前的旧名为 ``conversation_with_tool``）。
    返回 True 表示已保存，False 表示跳过。

    跳过条件：

    - 持久化未启用（``is_enabled() == False``）
    - agent 没有 ``uuid``（无法生成 key）
    - 后端未配置（理论上不会发生，因为 ``_read_env_config`` 必注册）
    """
    if not is_enabled():
        return False
    uuid_str = getattr(agent, "uuid", None)
    name_str = getattr(agent, "name", None)
    if not uuid_str and not name_str:
        return False
    key = uuid_str if backends.key_strategy == "uuid" else name_str
    if not key:
        return False
    try:
        state = export_state_dict(agent)
        get_backend().save(key, state)
        return True
    except Exception as e:
        # 自动保存失败不应阻塞对话；只记日志
        logger.warning(
            f"auto_save 失败（agent uuid={uuid_str} name={name_str}）: {e}"
        )
        return False


# ============================================================================
# Decorators: 包 conversation / aconversation（旧名 conversation_with_tool）
# ============================================================================
#
# 用 ``_conv_depth`` 计数器跟踪对话嵌套层数：
# - 外层调用：depth 0 → 1
# - 递归调用（如 BaseAgent FC 模式的 ``self.conversation()`` 续轮）：
#   depth 1 → 2 → 1（无 auto_save）
# - 最外层退出：depth 1 → 0 → 触发 auto_save(self)
# 这样保证每个 ``conversation`` 调用只自动保存 1 次（不重复）。
# 装饰的是函数对象本身，与方法名无关，所以 ``conversation`` 和 deprecated alias
# ``conversation_with_tool`` 都打上装饰器后会共享同一个 depth 计数器。

def _auto_save(method: Callable) -> Callable:
    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        self._conv_depth = getattr(self, "_conv_depth", 0) + 1
        try:
            return method(self, *args, **kwargs)
        finally:
            self._conv_depth -= 1
            if self._conv_depth == 0:
                auto_save(self)
    return wrapper


def _auto_save_async(method: Callable) -> Callable:
    @functools.wraps(method)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        self._conv_depth = getattr(self, "_conv_depth", 0) + 1
        try:
            return await method(self, *args, **kwargs)
        finally:
            self._conv_depth -= 1
            if self._conv_depth == 0:
                auto_save(self)
    return wrapper


# ============================================================================
# Sectioned INI parser / writer
# ============================================================================

class _SectionedFile:
    """INI 风格文件解析：[SECTION] / key = value / 行内 # 注释。"""

    @staticmethod
    def parse(text: str) -> Dict[str, Dict[str, str]]:
        sections: Dict[str, Dict[str, str]] = {}
        current: Optional[Dict[str, str]] = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current = {}
                sections[line[1:-1]] = current
                continue
            if current is None:
                raise FormatError(f"key=value before any section: {raw!r}")
            if "=" not in line:
                raise FormatError(f"malformed line: {raw!r}")
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()
        return sections

    @staticmethod
    def render(sections: Dict[str, Dict[str, str]], header_comments: Optional[List[str]] = None) -> str:
        lines: List[str] = list(header_comments or [])
        for name, kv in sections.items():
            lines.append(f"[{name}]")
            for k, v in kv.items():
                lines.append(f"{k} = {v}")
            lines.append("")
        return "\n".join(lines)


# ============================================================================
# State (de)serialization
# ============================================================================

def _class_to_path(cls: type) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def _path_to_class(path: str) -> type:
    module_name, _, qualname = path.partition(":")
    if not qualname:
        raise ValueError(f"invalid class path: {path!r}")
    module = importlib.import_module(module_name)
    obj: Any = module
    for part in qualname.split("."):
        obj = getattr(obj, part)
    if not isinstance(obj, type):
        raise TypeError(f"resolved {path!r} is not a class: {type(obj).__name__}")
    return obj


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat()


def _agent_protocol(agent: Any) -> str:
    proto = getattr(type(agent), "protocol", None)
    if proto:
        return str(proto)
    import tangyuanAI  # 延迟 import 避免循环
    if isinstance(agent, getattr(tangyuanAI, "AnthropicAgent", ())):
        return "anthropic"
    return "openai"


def _detect_api_key_env(agent: Any) -> Optional[str]:
    """反查 api_key 对应的环境变量名（找不到返回 None）。"""
    api_key = getattr(agent, "api_key", None) or ""
    if not api_key:
        return None
    for env_name, val in os.environ.items():
        if val == api_key:
            return env_name
    return None


def _collect_class_attrs(agent: Any) -> Dict[str, str]:
    """采集可序列化的类属性。"""
    keys = (
        "prompt", "api_provider", "model_name",
        "max_tokens", "stream", "fc_model",
        "tool_timeout", "tool_max_workers",
        "anthropic_version",  # 仅 AnthropicAgent
    )
    out: Dict[str, str] = {}
    cls = type(agent)
    for k in keys:
        v = getattr(cls, k, None)
        if v is None:
            continue
        out[k] = str(v)
    return out


def _hook_to_path(hook: Any) -> Optional[str]:
    """callable → 'module:qualname'；非顶层函数返回 None。"""
    try:
        if not callable(hook):
            return None
        if hasattr(hook, "__qualname__") and hasattr(hook, "__module__"):
            qn = hook.__qualname__
            mn = hook.__module__
            if mn and "<locals>" not in qn:
                return f"{mn}:{qn}"
        return None
    except Exception:
        return None


def export_state_dict(agent: Any) -> Dict[str, Any]:
    """把 agent 序列化为 dict（中间表示，不绑定具体后端）。"""
    cls = type(agent)
    api_key_env = _detect_api_key_env(agent)

    meta_lines: Dict[str, str] = {
        "format_version": str(FORMAT_VERSION),
        "schema_version": _get_schema_version(),
        "agent_uuid": agent.uuid or "",
        "agent_name": agent.name or "",
        "protocol": _agent_protocol(agent),
        "class": _class_to_path(cls),
        "saved_at": _now_iso(),
        "message_count": str(len(agent.history or [])),
    }

    config_lines: Dict[str, str] = {}
    for k, v in _collect_class_attrs(agent).items():
        # 多行字符串转义为 \n
        v_esc = v.replace("\\", "\\\\").replace("\n", "\\n")
        config_lines[k] = v_esc
    if api_key_env:
        config_lines["api_key_env"] = api_key_env

    state_lines: Dict[str, str] = {
        "current_task_id": agent.current_task_id or "",
    }
    hook_paths: List[str] = []
    for h in getattr(agent, "tool_call_hooks", []) or []:
        p = _hook_to_path(h)
        if p:
            hook_paths.append(p)
    if hook_paths:
        state_lines["hooks"] = json.dumps(hook_paths, ensure_ascii=False)

    history_lines: List[str] = []
    for msg in (agent.history or []):
        history_lines.append(json.dumps(msg, ensure_ascii=False))

    return {
        "_meta": meta_lines,
        "_config": config_lines,
        "_state": state_lines,
        "_history": history_lines,
    }


def export_state_string(agent: Any) -> str:
    """agent → 字符串（INI 头 + JSONL 体）。"""
    s = export_state_dict(agent)
    comments = [
        "# tangyuanAI Agent State File",
        f"# format: {FORMAT_NAME}/{FORMAT_VERSION}.0",
        "# https://github.com/secret-tangyuan/tangyuanAI",
        "# ===== DO NOT EDIT UNLESS YOU KNOW WHAT YOU'RE DOING =====",
        "",
    ]
    sections = {
        "META": s["_meta"],
        "CONFIG": s["_config"],
        "STATE": s["_state"],
    }
    rendered = _SectionedFile.render(sections, header_comments=comments)
    if s["_history"]:
        rendered += "[HISTORY]\n" + "\n".join(s["_history"]) + "\n"
    return rendered


def parse_state_string(text: str) -> Dict[str, Any]:
    """字符串 → 中间 dict。``_history`` 字段是 JSONL 行列表。"""
    lines = text.splitlines()
    # 先用 [SECTION] 切分；[HISTORY] 之前是 INI，[HISTORY] 之后是 JSONL
    in_history = False
    ini_text_lines: List[str] = []
    history_lines: List[str] = []
    for line in lines:
        if not in_history and line.strip() == "[HISTORY]":
            in_history = True
            continue
        if in_history:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                history_lines.append(stripped)
        else:
            ini_text_lines.append(line)
    sections = _SectionedFile.parse("\n".join(ini_text_lines))
    return {
        "_meta": sections.get("META", {}),
        "_config": sections.get("CONFIG", {}),
        "_state": sections.get("STATE", {}),
        "_history": history_lines,
    }


def _resolve_class(meta: Dict[str, str]) -> type:
    """按优先级解析类：[META].class → agent_list[uuid] → 报 AgentNotFoundError。"""
    class_path = meta.get("class", "")
    if class_path:
        try:
            return _path_to_class(class_path)
        except (ImportError, AttributeError, ValueError, TypeError) as e:
            _class_err = e
        else:
            _class_err = None
    else:
        _class_err = None

    # Fallback 1: agent_list[uuid]
    uuid_str = meta.get("agent_uuid", "")
    if uuid_str:
        import tangyuanAI
        if uuid_str in tangyuanAI.agent_list:
            return type(tangyuanAI.agent_list[uuid_str])

    msg = (
        f"无法解析 agent class：路径 {class_path!r} import 失败"
        if class_path
        else "无法解析 agent class：[META].class 缺失"
    )
    if uuid_str:
        msg += f"；agent_list 中也找不到 uuid={uuid_str!r}"
    msg += "。需要：[1] 修正 class 路径，或 [2] 提前 activate_template 让 agent_list 里有该 uuid"
    raise AgentNotFoundError(msg)


def _unescape(s: str) -> str:
    return s.replace("\\n", "\n").replace("\\\\", "\\")


def _apply_class_attrs(cls: type, config: Dict[str, str]) -> None:
    """把 [CONFIG] 字段写回类属性。"""
    for k, v in config.items():
        if k in {"api_key_env"}:
            continue
        if not hasattr(cls, k) and k not in {
            "prompt", "api_provider", "model_name",
            "max_tokens", "stream", "fc_model",
            "tool_timeout", "tool_max_workers",
            "anthropic_version",
        }:
            continue
        try:
            # 类型推断
            if k in {"stream", "fc_model"}:
                setattr(cls, k, v.lower() in {"1", "true", "yes"})
            elif k in {"max_tokens", "tool_max_workers"}:
                setattr(cls, k, int(v))
            elif k in {"tool_timeout"}:
                setattr(cls, k, float(v))
            else:
                setattr(cls, k, _unescape(v))
        except (AttributeError, TypeError, ValueError):
            pass  # skip 不支持设置的类属性


def _apply_api_key_env(cls: type, env_name: str) -> None:
    if env_name:
        setattr(cls, "api_key", os.getenv(env_name, "") or getattr(cls, "api_key", ""))


def load_state_string(text: str) -> Any:
    """字符串 → Agent 实例。

    解析顺序：
    1. 重建 / 复用类（[META].class → agent_list[uuid] → 报错）
    2. 实例化（``cls()``，会让 ``__init__`` 重置 history / system_prompt）
    3. 还原类属性（[CONFIG] → 类属性；api_key_env → os.getenv 重新解析）
    4. 还原 history（[HISTORY] JSONL → list[dict]）
    5. 还原 state（current_task_id / hooks）
    """
    parsed = parse_state_string(text)
    meta = parsed["_meta"]
    config = parsed["_config"]
    state = parsed["_state"]
    history_raw = parsed["_history"]

    # 版本校验
    fmt_v = int(meta.get("format_version", "0"))
    if fmt_v > FORMAT_VERSION:
        raise FormatError(
            f"state file format_version={fmt_v} > supported {FORMAT_VERSION}; "
            f"需要更新 tangyuanAI"
        )

    # 1. 解析类
    cls = _resolve_class(meta)

    # 2. 实例化（__init__ 会清空 history / system_prompt / _tool_runner）
    agent = cls()

    # 3. 还原类属性
    _apply_class_attrs(cls, config)
    _apply_api_key_env(cls, config.get("api_key_env", ""))

    # 4. 还原 headers（OpenAI 默认用 Bearer；Anthropic 用 x-api-key + anthropic-version）
    import tangyuanAI
    is_anthropic = isinstance(agent, getattr(tangyuanAI, "AnthropicAgent", ()))
    if is_anthropic:
        agent._build_system_prompt()
        agent.headers = {
            "x-api-key": agent.api_key or "",
            "anthropic-version": agent.anthropic_version,
            "Content-Type": "application/json",
        }
    else:
        agent.headers = {
            **({"Authorization": f"Bearer {agent.api_key}"} if hasattr(agent, "api_key") else {}),
            "Content-Type": "application/json",
        }

    # 5. 还原 history
    agent.history = [json.loads(line) for line in history_raw if line.strip()]  # noqa: SLF001

    # 6. 还原 state
    tid = state.get("current_task_id", "")  # noqa: SLF001
    if tid:
        agent.current_task_id = tid

    hook_paths_str = state.get("hooks", "[]")
    try:
        hook_paths = json.loads(hook_paths_str)
        for hp in hook_paths:
            try:
                hook = _path_to_class(hp)
                if callable(hook):
                    agent.register_tool_hook(hook)
            except (ImportError, AttributeError, ValueError, TypeError):
                pass  # 找不到的 hook 静默跳过
    except json.JSONDecodeError:
        pass

    return agent


# ============================================================================
# Top-level API
# ============================================================================

def save_state(
    agent: Any,
    key: str,
    *,
    backend: Optional[str] = None,
) -> None:
    """把 agent 状态保存到指定后端的指定 key。"""
    state = export_state_dict(agent)
    get_backend(backend).save(key, state)


def load_state(
    key: str,
    *,
    backend: Optional[str] = None,
) -> Any:
    """从指定后端加载 key 对应的 agent 状态，返回新 Agent 实例。"""
    state = get_backend(backend).load(key)
    # 还原成字符串再走 load_state_string（统一解析路径）
    sections: Dict[str, Dict[str, str]] = {
        "META": state.get("_meta", {}),
        "CONFIG": state.get("_config", {}),
        "STATE": state.get("_state", {}),
    }
    ini_text = _SectionedFile.render(sections)
    history_text = ""
    if state.get("_history"):
        history_text = "[HISTORY]\n" + "\n".join(state["_history"]) + "\n"
    return load_state_string(ini_text + history_text)


def delete_state(key: str, *, backend: Optional[str] = None) -> bool:
    return get_backend(backend).delete(key)


def list_states(*, backend: Optional[str] = None) -> List[str]:
    return get_backend(backend).list_keys()


# ============================================================================
# Built-in backends
# ============================================================================

class FileBackend:
    """默认后端：每个 key 一个 ``.tas`` 文件（兼容旧 ``.duas``）。"""

    name = "file"

    def __init__(self, base_dir: str = "./.tangyuanAI_sessions"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path_for(self, key: str) -> Path:
        if "/" in key or "\\" in key or ".." in key.split("/"):
            raise ValueError(f"invalid key: {key!r}")
        # v1.0.0：默认扩展名 .tas（旧 .duas 文件仍识别加载，向后兼容）。
        new = self.base_dir / f"{key}{CURRENT_EXT}"
        legacy = self.base_dir / f"{key}{LEGACY_EXT}"
        if legacy.exists() and not new.exists():
            return legacy
        return new

    def save(self, key: str, state: Dict[str, Any]) -> None:
        sections = {
            "META": state.get("_meta", {}),
            "CONFIG": state.get("_config", {}),
            "STATE": state.get("_state", {}),
        }
        comments = [
            "# tangyuanAI Agent State File",
            f"# format: {FORMAT_NAME}/{FORMAT_VERSION}.0",
            f"# saved_at: {state.get('_meta', {}).get('saved_at', _now_iso())}",
            "",
        ]
        rendered = _SectionedFile.render(sections, header_comments=comments)
        if state.get("_history"):
            rendered += "[HISTORY]\n" + "\n".join(state["_history"]) + "\n"
        path = self._path_for(key)
        temp_path = None
        with self._lock:
            try:
                fd, temp_name = tempfile.mkstemp(
                    prefix=f".{path.name}.", suffix=".tmp", dir=str(self.base_dir)
                )
                temp_path = Path(temp_name)
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                    handle.write(rendered)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, path)
                temp_path = None
            finally:
                if temp_path is not None:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError:
                        pass

    def load(self, key: str) -> Dict[str, Any]:
        with self._lock:
            path = self._path_for(key)
            if not path.exists():
                raise FileNotFoundError(f"state not found: {key!r} (path={path})")
            text = path.read_text(encoding="utf-8")
        parsed = parse_state_string(text)
        return {
            "_meta": parsed["_meta"],
            "_config": parsed["_config"],
            "_state": parsed["_state"],
            "_history": parsed["_history"],
        }

    def delete(self, key: str) -> bool:
        with self._lock:
            path = self._path_for(key)
            if path.exists():
                path.unlink()
                return True
            return False

    def list_keys(self) -> List[str]:
        with self._lock:
            return sorted(p.stem for p in self.base_dir.glob(f"*{CURRENT_EXT}"))


class SQLiteBackend:
    """实验性后端：用 sqlite3 存状态。

    表结构::

        CREATE TABLE sessions (
            key TEXT PRIMARY KEY,
            meta TEXT,        -- JSON
            config TEXT,      -- JSON
            state TEXT,       -- JSON
            history TEXT,     -- JSONL（多行用 \\n 分隔的 JSON 串）
            saved_at TEXT
        );

    注意：v0.3.2 初次实现，**未在大规模并发下压测**。生产前请充分测试。
    """

    name = "sqlite"

    def __init__(self, db_path: str = "./.tangyuanAI_sessions.db"):
        self.db_path = db_path
        self.timeout = 30.0
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    key TEXT PRIMARY KEY,
                    meta TEXT NOT NULL,
                    config TEXT NOT NULL,
                    state TEXT NOT NULL,
                    history TEXT NOT NULL,
                    saved_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save(self, key: str, state: Dict[str, Any]) -> None:
        history_text = "\n".join(state.get("_history", []))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions (key, meta, config, state, history, saved_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    json.dumps(state.get("_meta", {}), ensure_ascii=False),
                    json.dumps(state.get("_config", {}), ensure_ascii=False),
                    json.dumps(state.get("_state", {}), ensure_ascii=False),
                    history_text,
                    state.get("_meta", {}).get("saved_at", _now_iso()),
                ),
            )
            conn.commit()

    def load(self, key: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT meta, config, state, history FROM sessions WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"state not found in sqlite: {key!r}")
        history_text = row["history"] or ""
        return {
            "_meta": json.loads(row["meta"]),
            "_config": json.loads(row["config"]),
            "_state": json.loads(row["state"]),
            "_history": [line for line in history_text.split("\n") if line.strip()],
        }

    def delete(self, key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE key = ?", (key,))
            conn.commit()
        return cur.rowcount > 0

    def list_keys(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key FROM sessions ORDER BY saved_at").fetchall()
        return [r["key"] for r in rows]


# 注册默认后端
register_backend("file", FileBackend(), set_as_default=True)
register_backend("sqlite", SQLiteBackend(), set_as_default=False)
