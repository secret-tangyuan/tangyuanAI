"""tool_reliability.py 单元测试。"""
from __future__ import annotations

import time
from pydantic import BaseModel
from tangyuanAI.tool_reliability import (
    IdempotencyStore,
    RetryPolicy,
    VerifiableToolResult,
    get_default_idempotency_store,
    reset_default_idempotency_store,
    run_with_retry,
    validate_output,
)


def test_validate_output_passthrough_when_no_schema():
    ok, err, value = validate_output({"a": 1}, None)
    assert ok is True
    assert err is None
    assert value == {"a": 1}


def test_validate_output_success():
    class S(BaseModel):
        x: int
        y: str

    ok, err, value = validate_output({"x": 1, "y": "hi"}, S)
    assert ok is True
    assert value == {"x": 1, "y": "hi"}


def test_validate_output_failure():
    class S(BaseModel):
        x: int
        y: str

    ok, err, value = validate_output({"x": "wrong", "y": "hi"}, S)
    assert ok is False
    assert err is not None
    assert value is None


def test_retry_policy_should_retry_timeout():
    p = RetryPolicy()
    assert p.should_retry(TimeoutError()) is True
    assert p.should_retry(ValueError()) is False


def test_retry_policy_backoff_caps():
    p = RetryPolicy(backoff_base=0.1, backoff_cap=1.0, jitter=0.0)
    assert p.compute_backoff(1) == 0.1
    assert p.compute_backoff(2) == 0.2
    assert p.compute_backoff(3) == 0.4
    assert p.compute_backoff(20) == 1.0  # capped


def test_run_with_retry_eventually_succeeds():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("transient")
        return "ok"

    result = run_with_retry(flaky, args={}, policy=RetryPolicy(max=5, backoff_base=0.001))
    assert result == "ok"
    assert calls["n"] == 3


def test_run_with_retry_gives_up_on_non_retryable():
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise ValueError("nope")

    import pytest
    with pytest.raises(ValueError):
        run_with_retry(boom, args={}, policy=RetryPolicy(max=3))
    assert calls["n"] == 1  # 不重试


def test_idempotency_store_basic_hit_miss():
    reset_default_idempotency_store()
    store = get_default_idempotency_store()
    store.clear()
    key = b"\x00" * 32

    # miss
    assert store.get(key) is None

    # set + hit
    r = VerifiableToolResult(ok=True, value="result-1", schema_validated=False)
    store.set(key, r)
    hit = store.get(key)
    assert hit is not None
    assert hit.value == "result-1"


def test_idempotency_store_key_stable_for_same_input():
    a = IdempotencyStore.compute_key("agent-1", "call-1", "get_weather", {"city": "Beijing"})
    b = IdempotencyStore.compute_key("agent-1", "call-1", "get_weather", {"city": "Beijing"})
    c = IdempotencyStore.compute_key("agent-1", "call-2", "get_weather", {"city": "Beijing"})
    d = IdempotencyStore.compute_key("agent-1", "call-1", "get_weather", {"city": "Tianjin"})

    assert a == b
    assert a != c  # tool_call_id 不同
    assert a != d  # args 不同
    assert all(isinstance(k, bytes) and len(k) == 32 for k in (a, b, c, d))


def test_idempotency_store_ttl_expiry():
    store = IdempotencyStore(default_ttl=0.05)
    key = b"\x01" * 32
    store.set(key, VerifiableToolResult(ok=True, value="x"))
    assert store.get(key) is not None
    time.sleep(0.1)
    assert store.get(key) is None


def test_idempotency_store_lru_eviction():
    store = IdempotencyStore(default_ttl=60, max_size=3)
    for i in range(4):
        store.set(bytes([i]) + b"\x00" * 31, VerifiableToolResult(ok=True, value=i))
    # 第一个被 evict
    assert store.get(b"\x00\x00" * 16) is None
    assert store.get(bytes([3]) + b"\x00" * 31) is not None


def test_verifiable_tool_result_to_dict():
    r = VerifiableToolResult(ok=False, error="boom", raw="raw_value", retry_count=2)
    d = r.to_dict()
    assert d["ok"] is False
    assert d["error"] == "boom"
    assert d["raw"] == "raw_value"
    assert d["retry_count"] == 2


def test_register_tool_stores_reliability_metadata():
    """agent_tool.register_tool 应该把 output_schema / retry / idempotency_ttl 存到 _tools。"""
    from tangyuanAI import tool_registry
    from tangyuanAI.tool_reliability import RetryPolicy

    class MyResult(BaseModel):
        x: int

    @tool_registry.register_tool(
        name="sample_with_reliability",
        description="demo",
        parameters={"type": "object", "properties": {}, "required": []},
        output_schema=MyResult,
        retry=RetryPolicy(max=1),
        idempotency_ttl=42,
        overwrite=True,
    )
    def sample_with_reliability() -> dict:
        return {"x": 1}

    info = tool_registry.get_tool_info("sample_with_reliability")
    assert info is not None
    assert info["output_schema"] is MyResult
    assert info["retry"].max == 1
    assert info["idempotency_ttl"] == 42