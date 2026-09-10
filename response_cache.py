"""tangyuanAI response cache —— v1.4.0 引入的 LLM 响应缓存。

设计目标:
- 相同 ChatRequest 不重复打 LLM(节省 token / 延迟)
- 默认 ON,key = sha256({model, system, messages, tools, temperature})
- 命中条件: temperature == 0 AND tools 为空 OR 显式 cache_writes=True
- TTL 默认 1h
- 后端:MemoryBackend (LRU dict) / SQLiteBackend (用 stdlib sqlite3)

行为:
- cache hit → 直接返回 LLMResponse,不调 transport
- cache miss → 调 transport,set 进 cache 再返回
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

from .llm_transport import ChatRequest, LLMResponse

_logger = logging.getLogger(__name__)


# ============================================================
# Key 派生
# ============================================================


def cache_key(req: ChatRequest) -> bytes:
    """key = sha256({model, system, messages, tools, temperature, stream}) 排序 JSON。

    不含 stream(故意 — stream 是协议层开关,不影响 content)。
    """
    payload = {
        "model": req.model,
        "system": req.system,
        "messages": req.messages,
        "tools": req.tools,
        "temperature": req.temperature,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).digest()


def is_cacheable(req: ChatRequest) -> bool:
    """默认: temperature == 0 且无 tools 才 cache。

    显式 `req.extra["cache_writes"] = True` 强制 cache(无论 temperature)。
    """
    if req.extra and req.extra.get("cache_writes"):
        return True
    if req.temperature and req.temperature != 0:
        return False
    if req.tools:
        return False
    return True


# ============================================================
# Backends
# ============================================================


class ResponseCacheBackend(ABC):
    @abstractmethod
    def get(self, key: bytes) -> Optional[LLMResponse]: ...

    @abstractmethod
    def set(self, key: bytes, value: LLMResponse, ttl: float) -> None: ...

    @abstractmethod
    def delete(self, key: bytes) -> bool: ...

    @abstractmethod
    def clear(self) -> None: ...

    @abstractmethod
    def stats(self) -> dict: ...


class MemoryBackend(ResponseCacheBackend):
    """LRU dict + per-entry expiry."""

    def __init__(self, max_size: int = 4096):
        self.max_size = max_size
        self._data: dict[bytes, tuple[LLMResponse, float]] = {}
        self._order: list[bytes] = []  # LRU 顺序

    def get(self, key: bytes) -> Optional[LLMResponse]:
        entry = self._data.get(key)
        if entry is None:
            return None
        rsp, expires_at = entry
        if expires_at < time.time():
            del self._data[key]
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
        return rsp

    def set(self, key: bytes, value: LLMResponse, ttl: float) -> None:
        if key in self._data:
            try:
                self._order.remove(key)
            except ValueError:
                pass
        elif len(self._data) >= self.max_size:
            oldest = self._order.pop(0)
            del self._data[oldest]
        self._data[key] = (value, time.time() + ttl)
        self._order.append(key)

    def delete(self, key: bytes) -> bool:
        if key in self._data:
            del self._data[key]
            try:
                self._order.remove(key)
            except ValueError:
                pass
            return True
        return False

    def clear(self) -> None:
        self._data.clear()
        self._order.clear()

    def stats(self) -> dict:
        return {"backend": "memory", "size": len(self._data), "max_size": self.max_size}


class SQLiteBackend(ResponseCacheBackend):
    """用 stdlib sqlite3 持久化。适合跨进程共享。"""

    def __init__(self, db_path: str = "logs/response_cache.sqlite"):
        import os
        import sqlite3
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key BLOB PRIMARY KEY, value BLOB, expires_at REAL)"
        )
        self._conn.commit()

    def get(self, key: bytes) -> Optional[LLMResponse]:
        cur = self._conn.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        value_blob, expires_at = row
        if expires_at < time.time():
            self.delete(key)
            return None
        try:
            data = json.loads(value_blob.decode("utf-8"))
            return _llm_response_from_dict(data)
        except Exception as e:
            _logger.warning(f"cache value 反序列化失败: {e}")
            return None

    def set(self, key: bytes, value: LLMResponse, ttl: float) -> None:
        # 序列化 LLMResponse 为 dict
        try:
            data = _llm_response_to_dict(value)
            blob = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        except Exception as e:
            _logger.warning(f"cache value 序列化失败: {e}")
            return
        expires_at = time.time() + ttl
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, blob, expires_at),
        )
        self._conn.commit()

    def delete(self, key: bytes) -> bool:
        cur = self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        self._conn.commit()
        return cur.rowcount > 0

    def clear(self) -> None:
        self._conn.execute("DELETE FROM cache")
        self._conn.commit()

    def stats(self) -> dict:
        cur = self._conn.execute("SELECT COUNT(*) FROM cache")
        n = cur.fetchone()[0]
        return {"backend": "sqlite", "size": n, "db_path": self.db_path}


def _llm_response_to_dict(rsp: LLMResponse) -> dict:
    """LLMResponse → 可 JSON 序列化的 dict。"""
    return {
        "text": rsp.text,
        "tool_calls": [
            {
                "id": tc.id,
                "name": tc.name,
                "arguments": tc.arguments,
            }
            for tc in rsp.tool_calls
        ],
        "stop_reason": rsp.stop_reason,
        "usage": {
            "prompt_tokens": rsp.usage.prompt_tokens,
            "completion_tokens": rsp.usage.completion_tokens,
            "total_tokens": rsp.usage.total_tokens,
        } if rsp.usage else None,
        "raw": rsp.raw,
    }


def _llm_response_from_dict(d: dict) -> LLMResponse:
    """反序列化回 LLMResponse。"""
    from .llm_transport import ToolCall, UsageInfo
    tool_calls = [
        ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
        for tc in d.get("tool_calls", [])
    ]
    usage_dict = d.get("usage")
    usage = None
    if usage_dict:
        usage = UsageInfo(
            prompt_tokens=usage_dict.get("prompt_tokens", 0),
            completion_tokens=usage_dict.get("completion_tokens", 0),
            total_tokens=usage_dict.get("total_tokens", 0),
        )
    return LLMResponse(
        text=d.get("text", ""),
        tool_calls=tool_calls,
        stop_reason=d.get("stop_reason"),
        usage=usage,
        raw=d.get("raw"),
    )


# ============================================================
# CachedTransport wrapper
# ============================================================


class CachedTransport:
    """包一个 transport,命中 cache 直接返回 LLMResponse,不调 transport。"""

    def __init__(self, inner, backend: ResponseCacheBackend, default_ttl: float = 3600.0):
        self.inner = inner
        self.backend = backend
        self.default_ttl = default_ttl

    def chat(self, req: ChatRequest) -> LLMResponse:
        key = cache_key(req)
        if is_cacheable(req):
            hit = self.backend.get(key)
            if hit is not None:
                return hit
        rsp = self.inner.chat(req)
        if is_cacheable(req):
            self.backend.set(key, rsp, self.default_ttl)
        return rsp

    async def achat(self, req: ChatRequest) -> LLMResponse:
        key = cache_key(req)
        if is_cacheable(req):
            hit = self.backend.get(key)
            if hit is not None:
                return hit
        rsp = await self.inner.achat(req)
        if is_cacheable(req):
            self.backend.set(key, rsp, self.default_ttl)
        return rsp


# 全局默认 cache (默认 OFF — 由 feature config 决定)
_default_backend: Optional[ResponseCacheBackend] = None


def get_default_cache_backend() -> Optional[ResponseCacheBackend]:
    return _default_backend


def set_default_cache_backend(backend: Optional[ResponseCacheBackend]) -> None:
    global _default_backend
    _default_backend = backend


__all__ = [
    "cache_key",
    "is_cacheable",
    "ResponseCacheBackend",
    "MemoryBackend",
    "SQLiteBackend",
    "CachedTransport",
    "get_default_cache_backend",
    "set_default_cache_backend",
]
