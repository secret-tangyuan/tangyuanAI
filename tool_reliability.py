"""tangyuanAI tool reliability —— v1.4.0 引入的工具可靠性层。

核心目标:把"静默 tool 失败"从行业典型 23% 降到接近 0。
LLM 看到的 tool_result 永远是**结构化**(成功值或显式失败),不再"幻觉成功"。

3 大机制:
1. **输出校验** —— pydantic schema 校验 tool 返回值,失败 → `{"ok": false, "error": "...", "raw": ...}`
2. **自动重试** —— transient 异常(超时 / 连接 / 5xx)默认 2 次重试,policy 用 tenacity
3. **idempotency** —— 相同 (agent, tool, args) 默认 1h LRU cache,防止重复副作用

API:
- `@tool_registry.register_tool(output_schema=MyResult, retry=RetryPolicy(...), idempotency_ttl=3600)`
- LLM 看到 `VerifiableToolResult` 序列化:`{"ok": bool, "value": Any, "error": str?, "raw": Any, "schema_validated": bool}`
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Type

_logger = logging.getLogger(__name__)


# ============================================================
# RetryPolicy
# ============================================================


@dataclass
class RetryPolicy:
    """工具自动重试策略。

    默认 max=2 (首次 + 1 重试);backoff 默认 0.5s base, 8s cap, 0.25 jitter。
    retryable 默认只覆盖 transient 异常(超时 / 连接 / API 5xx)。
    """

    max: int = 2
    backoff_base: float = 0.5
    backoff_cap: float = 8.0
    jitter: float = 0.25

    # retryable 在 import 时注入具体异常类;默认 (TimeoutError, ConnectionError, OSError)
    retryable: tuple = field(default_factory=lambda: (TimeoutError, ConnectionError, OSError))

    def should_retry(self, exc: BaseException) -> bool:
        return isinstance(exc, self.retryable)

    def compute_backoff(self, attempt: int) -> float:
        """attempt = 1, 2, ... 第 N 次重试前等待秒数。"""
        import random

        delay = min(self.backoff_base * (2 ** (attempt - 1)), self.backoff_cap)
        if self.jitter:
            delay += random.uniform(-self.jitter * delay, self.jitter * delay)
        return max(0.0, delay)


# ============================================================
# VerifiableToolResult
# ============================================================


@dataclass
class VerifiableToolResult:
    """tool 调用的结构化结果。LLM 看到的 tool_result 序列化自此。

    ok=True → value 是真实返回值(或 pydantic 校验后的 dump)
    ok=False → LLM 看到结构化失败,可据此决定重试 / 改 plan / 跳过
    """

    ok: bool
    value: Any = None
    error: Optional[str] = None
    raw: Any = None
    schema_validated: bool = False
    retry_count: int = 0

    def to_dict(self) -> dict:
        """序列化进 history 的 JSON 形式。"""
        return {
            "ok": self.ok,
            "value": self.value,
            "error": self.error,
            "raw": self.raw,
            "schema_validated": self.schema_validated,
            "retry_count": self.retry_count,
        }


# ============================================================
# Output validation
# ============================================================


def validate_output(value: Any, schema: Optional[Type]) -> tuple:
    """用 pydantic schema 校验 value。

    返回 (ok, error_msg, validated_value):
    - ok=True: validated_value 是 pydantic.model_dump()
    - ok=False: error_msg 描述校验失败原因;validated_value 是 None
    - schema is None: pass-through, ok=True, value=raw
    """
    if schema is None:
        return True, None, value
    try:
        # schema 是 BaseModel 子类
        instance = schema.model_validate(value)
        return True, None, instance.model_dump()
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", None


# ============================================================
# Idempotency
# ============================================================


@dataclass
class _CacheEntry:
    result: VerifiableToolResult
    expires_at: float


class IdempotencyStore:
    """tool idempotency LRU cache + TTL。

    key = sha256(agent_uuid + tool_name + canonical_args_json + tool_call_id)
    """

    def __init__(self, default_ttl: float = 3600.0, max_size: int = 1024):
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._entries: dict[bytes, _CacheEntry] = {}
        # 按插入顺序保持 LRU
        self._order: list[bytes] = []

    @staticmethod
    def compute_key(
        agent_uuid: str,
        tool_call_id: str,
        tool_name: str,
        args: dict,
    ) -> bytes:
        canonical = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        h = hashlib.sha256()
        h.update(agent_uuid.encode("utf-8"))
        h.update(b"\x00")
        h.update(tool_call_id.encode("utf-8"))
        h.update(b"\x00")
        h.update(tool_name.encode("utf-8"))
        h.update(b"\x00")
        h.update(canonical.encode("utf-8"))
        return h.digest()

    def get(self, key: bytes) -> Optional[VerifiableToolResult]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.time():
            # expired
            del self._entries[key]
            try:
                self._order.remove(key)
            except ValueError:
                pass
            return None
        # 命中 → 移到 MRU
        try:
            self._order.remove(key)
        except ValueError:
            pass
        self._order.append(key)
        # 标记 cache hit
        return VerifiableToolResult(
            ok=entry.result.ok,
            value=entry.result.value,
            error=entry.result.error,
            raw=entry.result.raw,
            schema_validated=entry.result.schema_validated,
            retry_count=entry.result.retry_count,
        )

    def set(self, key: bytes, result: VerifiableToolResult, ttl: Optional[float] = None) -> None:
        if key in self._entries:
            try:
                self._order.remove(key)
            except ValueError:
                pass
        elif len(self._entries) >= self.max_size:
            # LRU evict
            oldest = self._order.pop(0)
            del self._entries[oldest]
        self._entries[key] = _CacheEntry(
            result=result,
            expires_at=time.time() + (ttl if ttl is not None else self.default_ttl),
        )
        self._order.append(key)

    def clear(self) -> None:
        self._entries.clear()
        self._order.clear()


# 全局默认 idempotency store (per-process)
_default_store = IdempotencyStore()


def get_default_idempotency_store() -> IdempotencyStore:
    return _default_store


def reset_default_idempotency_store() -> None:
    """测试用:清空全局 store。"""
    global _default_store
    _default_store = IdempotencyStore()


# ============================================================
# Run with retry
# ============================================================


def run_with_retry(
    func: Callable,
    *,
    args: dict,
    policy: RetryPolicy,
    on_each_attempt: Optional[Callable[[int], None]] = None,
) -> Any:
    """执行 func(**args) 带 policy 重试。

    返回 func 的实际返回值。policy.max 是总尝试次数(含首次)。
    transient 异常按 policy.retryable 重试;非 retryable 立即抛。
    on_each_attempt(attempt_idx) 在每次重试前回调,attempt_idx=1 表示第 1 次重试(首次已失败)。
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(1, policy.max + 1):
        try:
            return func(**args) if args else func()
        except BaseException as e:
            last_exc = e
            if attempt >= policy.max or not policy.should_retry(e):
                raise
            if on_each_attempt:
                on_each_attempt(attempt)
            time.sleep(policy.compute_backoff(attempt))
    # unreachable,但让 type checker 满意
    if last_exc:
        raise last_exc
    raise RuntimeError("run_with_retry reached unreachable state")


__all__ = [
    "RetryPolicy",
    "VerifiableToolResult",
    "validate_output",
    "IdempotencyStore",
    "get_default_idempotency_store",
    "reset_default_idempotency_store",
    "run_with_retry",
]