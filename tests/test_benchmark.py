# -*- coding: utf-8 -*-
"""
最小性能 benchmark（v0.4.1+）。

**不**依赖 pytest-benchmark（避免新增 dev 依赖），纯 ``time.perf_counter`` 跑 N 次
取分位数。这是 smoke benchmark：抓回归、估量级，不是 perf 工程。

跑法::

    uv run pytest tests/test_benchmark.py -v -s

会输出每个场景的 P50 / P95 / P99 / mean（毫秒）。

注意：
- 这些测试不是"单测"（不验证功能），是基准。失败 = 性能回归 ≥ 2x。
- ``pytest -m "not benchmark"`` 跳过（标记）。
"""
from __future__ import annotations

import time
import uuid as _uuid
from statistics import mean

import pytest
from _llm_mock import (
    MockState,
    _AnthropicMockHandler,
    _start_mock_server,
    anthropic_text_response,
    anthropic_tool_use_response,
)
from tangyuanAI import (
    Agent,
    activate_template,
    agent_list,
    template_agent,
    tool_registry,
)
from tangyuanAI.persistence import (
    FileBackend,
    SQLiteBackend,
)

# 标记：默认 pytest 跳过，需要显式 ``pytest tests/test_benchmark.py`` 才跑
pytestmark = pytest.mark.benchmark


def _percentile(sorted_data, p):
    """手算分位数（不依赖 numpy）"""
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(sorted_data) - 1)
    if f == c:
        return sorted_data[f]
    return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)


def _report(name: str, samples):
    """打印 benchmark 结果到 stderr（pytest -s 才会显示）"""
    samples_sorted = sorted(samples)
    p50 = _percentile(samples_sorted, 50)
    p95 = _percentile(samples_sorted, 95)
    p99 = _percentile(samples_sorted, 99)
    avg = mean(samples)
    print(
        f"\n[BENCH] {name}: n={len(samples)} "
        f"P50={p50:.2f}ms P95={p95:.2f}ms P99={p99:.2f}ms mean={avg:.2f}ms",
        flush=True,
    )


# ===========================================================================
# 1. 端到端对话吞吐
# ===========================================================================

@pytest.fixture
def anthropic_bench_mock():
    state = MockState()
    _AnthropicMockHandler.state = state
    base_url, server = _start_mock_server(_AnthropicMockHandler)
    yield state, base_url, server
    server.shutdown()
    server.server_close()
    _AnthropicMockHandler.state = None


def _make_bench_agent(name: str, base_url: str):
    @template_agent(name, uuid=_uuid.uuid4().hex, description="bench")
    class _A(Agent):
        protocol = "anthropic"
        prompt = "p"
        model_name = "m"
        api_key = "k"
        api_provider = base_url
        stream = False

    activate_template(name)
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001
    return inst


def test_bench_anthropic_pure_text_throughput(anthropic_bench_mock):
    """Anthropic 纯文本对话吞吐（每轮 1 次 LLM 调用）"""
    state, base_url, server = anthropic_bench_mock
    agent = _make_bench_agent("bench-text", base_url)

    n = 30
    samples = []
    for i in range(n):
        # 每轮返不同文本
        state.queue(lambda _b, i=i: anthropic_text_response(f"reply {i}"))
        start = time.perf_counter()
        out = agent.conversation(f"hi {i}")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert out == f"reply {i}"
        samples.append(elapsed_ms)

    _report("anthropic_pure_text (n=30)", samples)
    # 软性断言：P95 < 100ms（mock 速度，实际 LLM 会慢很多）
    # 这只是防止严重性能回归，不强制
    # p95 = _percentile(sorted(samples), 95)
    # assert p95 < 100, f"regression: P95={p95:.1f}ms"


# ===========================================================================
# 2. 工具调用延迟
# ===========================================================================

def test_bench_anthropic_tool_call_latency(anthropic_bench_mock):
    """Anthropic 工具调用延迟（每轮 1 次 LLM + 1 次 tool execution）"""
    state, base_url, server = anthropic_bench_mock
    agent = _make_bench_agent("bench-tool", base_url)

    @tool_registry.register_tool(
        allowed_agents=["bench-tool"],
        name="echo",
        description="echo",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    )
    def echo(text: str) -> str:
        return f"echo:{text}"

    n = 20
    samples = []
    for i in range(n):
        # 每轮 2 步：tool_call + text
        state.queue(lambda _b, i=i: anthropic_tool_use_response(f"t{i}", "echo", {"text": f"msg{i}"}))
        state.queue(lambda _b, i=i: anthropic_text_response(f"done {i}"))
        start = time.perf_counter()
        out = agent.conversation(f"ask {i}")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert f"done {i}" in out
        samples.append(elapsed_ms)

    _report("anthropic_tool_call_2_turns (n=20)", samples)


# ===========================================================================
# 3. 持久化吞吐量（File + SQLite）
# ===========================================================================

@pytest.fixture
def tmp_bench_dir(tmp_path):
    """隔离的 bench 目录"""
    return tmp_path


def test_bench_file_backend_save_load(tmp_bench_dir):
    """FileBackend save + load 吞吐"""
    backend = FileBackend(base_dir=str(tmp_bench_dir))
    state = {
        "_meta": {"agent_uuid": "x", "format_version": "1", "schema_version": "0.4.1"},
        "_config": {"prompt": "a" * 200, "model_name": "x", "api_provider": "http://x"},
        "_state": {"current_task_id": "tid"},
        "_history": [
            '{"role":"user","content":"' + "x" * 500 + '"}',
            '{"role":"assistant","content":"y"}',
        ] * 30,  # 60 条 history
    }
    n = 100
    samples_save = []
    samples_load = []
    for i in range(n):
        key = f"k{i}"
        start = time.perf_counter()
        backend.save(key, state)
        samples_save.append((time.perf_counter() - start) * 1000)

        start = time.perf_counter()
        _ = backend.load(key)
        samples_load.append((time.perf_counter() - start) * 1000)

    _report("file_backend.save (n=100, hist=60)", samples_save)
    _report("file_backend.load (n=100, hist=60)", samples_load)


def test_bench_sqlite_backend_save_load(tmp_bench_dir):
    """SQLiteBackend save + load 吞吐"""
    backend = SQLiteBackend(db_path=str(tmp_bench_dir / "bench.db"))
    state = {
        "_meta": {"agent_uuid": "x", "format_version": "1"},
        "_config": {"prompt": "a" * 200},
        "_state": {"current_task_id": "tid"},
        "_history": [
            '{"role":"user","content":"' + "x" * 500 + '"}',
        ] * 30,
    }
    n = 100
    samples_save = []
    samples_load = []
    for i in range(n):
        key = f"k{i}"
        start = time.perf_counter()
        backend.save(key, state)
        samples_save.append((time.perf_counter() - start) * 1000)

        start = time.perf_counter()
        _ = backend.load(key)
        samples_load.append((time.perf_counter() - start) * 1000)

    _report("sqlite_backend.save (n=100, hist=30)", samples_save)
    _report("sqlite_backend.load (n=100, hist=30)", samples_load)
