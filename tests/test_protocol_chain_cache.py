"""protocol_chain + response_cache 单元测试。"""
from __future__ import annotations

import pytest
from tangyuanAI.errors import APIError
from tangyuanAI.llm_transport import (
    ChatRequest,
    LLMEvent,
    LLMResponse,
    LLMTransport,
    UsageInfo,
)
from tangyuanAI.protocol_chain import (
    AllProvidersFailed,
    ProtocolChainTransport,
)
from tangyuanAI.response_cache import (
    CachedTransport,
    MemoryBackend,
    cache_key,
    is_cacheable,
)

# ============================================================
# Mock transport helpers
# ============================================================


class MockTransport(LLMTransport):
    """测试用:每次调用记录,返回预定结果或抛异常。"""

    def __init__(self, *, raises: Exception = None, text: str = "ok", calls: list = None):
        self.raises = raises
        self.text = text
        self.calls = calls if calls is not None else []

    def chat(self, req):
        self.calls.append(req)
        if self.raises:
            raise self.raises
        return LLMResponse(
            text=self.text,
            tool_calls=[],
            stop_reason="stop",
            usage=UsageInfo(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    async def achat(self, req):
        return self.chat(req)

    def chat_stream(self, req):
        yield LLMEvent(type="text", text=self.text)
        yield LLMEvent(type="done")

    async def achat_stream(self, req):
        yield LLMEvent(type="text", text=self.text)
        yield LLMEvent(type="done")


def _make_req(text: str = "hi", tools=None, temperature: float = 0) -> ChatRequest:
    return ChatRequest(
        model="gpt-5",
        system=None,
        messages=[{"role": "user", "content": text}],
        tools=tools,
        stream=False,
        temperature=temperature,
    )


# ============================================================
# ProtocolChainTransport tests
# ============================================================


def test_chain_first_provider_succeeds_no_fallback():
    p1 = MockTransport(text="from-1")
    p2 = MockTransport(text="from-2")
    chain = ProtocolChainTransport([p1, p2], provider_names=["p1", "p2"])

    rsp = chain.chat(_make_req())

    assert rsp.text == "from-1"
    assert len(p1.calls) == 1
    assert len(p2.calls) == 0


def test_chain_falls_back_on_transient_error():
    p1 = MockTransport(raises=APIError("rate-limited"))
    p2 = MockTransport(text="from-2")
    chain = ProtocolChainTransport([p1, p2], provider_names=["p1", "p2"])

    rsp = chain.chat(_make_req())
    assert rsp.text == "from-2"
    assert len(p1.calls) == 1
    assert len(p2.calls) == 1


def test_chain_falls_back_on_timeout_and_connection():
    p1 = MockTransport(raises=TimeoutError())
    p2 = MockTransport(raises=ConnectionError())
    p3 = MockTransport(text="from-3")
    chain = ProtocolChainTransport([p1, p2, p3], provider_names=["p1", "p2", "p3"])

    rsp = chain.chat(_make_req())
    assert rsp.text == "from-3"


def test_chain_all_providers_failed_raises_combined():
    p1 = MockTransport(raises=APIError("e1"))
    p2 = MockTransport(raises=APIError("e2"))
    chain = ProtocolChainTransport([p1, p2], provider_names=["p1", "p2"])

    with pytest.raises(AllProvidersFailed) as exc_info:
        chain.chat(_make_req())
    assert len(exc_info.value.errors) == 2


def test_chain_does_not_fall_back_on_non_retryable_exception():
    """ValueError 不是 transient — 不应 fallback,直接 raise。"""
    p1 = MockTransport(raises=ValueError("programming bug"))
    p2 = MockTransport(text="should-not-run")
    chain = ProtocolChainTransport([p1, p2], provider_names=["p1", "p2"])

    with pytest.raises(ValueError):
        chain.chat(_make_req())
    assert len(p1.calls) == 1
    assert len(p2.calls) == 0


def test_chain_constructor_rejects_empty():
    with pytest.raises(ValueError):
        ProtocolChainTransport([])


# ============================================================
# Response cache tests
# ============================================================


def test_cache_key_is_stable_for_same_input():
    a = cache_key(_make_req("hi"))
    b = cache_key(_make_req("hi"))
    assert a == b
    assert isinstance(a, bytes) and len(a) == 32


def test_cache_key_differs_for_different_temperature():
    a = cache_key(_make_req(temperature=0))
    b = cache_key(_make_req(temperature=0.5))
    assert a != b


def test_cache_key_differs_for_different_messages():
    a = cache_key(_make_req("hi"))
    b = cache_key(_make_req("hello"))
    assert a != b


def test_is_cacheable_default_zero_temp_no_tools():
    req = _make_req()
    assert is_cacheable(req) is True


def test_is_cacheable_rejects_non_zero_temp():
    req = _make_req(temperature=0.7)
    assert is_cacheable(req) is False


def test_is_cacheable_rejects_with_tools():
    req = _make_req(tools=[{"type": "function"}])
    assert is_cacheable(req) is False


def test_is_cacheable_forced_by_cache_writes():
    req = _make_req(temperature=0.7, tools=[{"type": "function"}])
    req.extra["cache_writes"] = True
    assert is_cacheable(req) is True


def test_memory_backend_basic_get_set():
    b = MemoryBackend()
    rsp = LLMResponse(
        text="hello",
        tool_calls=[],
        stop_reason="stop",
        usage=UsageInfo(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    key = b"x" * 32
    assert b.get(key) is None
    b.set(key, rsp, ttl=60)
    got = b.get(key)
    assert got is not None
    assert got.text == "hello"


def test_memory_backend_ttl_expiry():
    b = MemoryBackend()
    rsp = LLMResponse(text="x", tool_calls=[], stop_reason="stop", usage=None)
    key = b"y" * 32
    b.set(key, rsp, ttl=0.05)
    assert b.get(key) is not None
    import time
    time.sleep(0.1)
    assert b.get(key) is None


def test_memory_backend_lru_eviction():
    b = MemoryBackend(max_size=3)
    rsp = LLMResponse(text="x", tool_calls=[], stop_reason="stop", usage=None)
    for i in range(4):
        b.set(bytes([i]) + b"\x00" * 31, rsp, ttl=60)
    assert b.get(b"\x00\x00" * 16) is None  # 第一个被 evict
    assert b.get(bytes([3]) + b"\x00" * 31) is not None


def test_cached_transport_avoids_inner_call_on_hit():
    inner = MockTransport(text="cached-reply")
    cache = MemoryBackend()
    cached = CachedTransport(inner, cache, default_ttl=60)

    # 第一次调:miss → inner.chat 调 1 次
    rsp1 = cached.chat(_make_req("hi"))
    assert rsp1.text == "cached-reply"
    assert len(inner.calls) == 1

    # 第二次调:hit → inner.chat 不调
    rsp2 = cached.chat(_make_req("hi"))
    assert rsp2.text == "cached-reply"
    assert len(inner.calls) == 1


def test_cached_transport_skips_cache_when_not_cacheable():
    inner = MockTransport(text="not-cached")
    cache = MemoryBackend()
    cached = CachedTransport(inner, cache, default_ttl=60)

    cached.chat(_make_req(temperature=0.7))  # 不 cache
    cached.chat(_make_req(temperature=0.7))
    # inner 应该被调 2 次(每次都 miss,不写 cache)
    assert len(inner.calls) == 2


def test_cached_transport_forced_cache_with_cache_writes_extra():
    inner = MockTransport(text="force-cached")
    cache = MemoryBackend()
    cached = CachedTransport(inner, cache, default_ttl=60)

    req = _make_req(temperature=0.7, tools=[{"type": "function"}])
    req.extra["cache_writes"] = True

    cached.chat(req)
    cached.chat(req)
    assert len(inner.calls) == 1  # 第二次命中
