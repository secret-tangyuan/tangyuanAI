"""tracing.py 单元测试。"""
from __future__ import annotations

import json

from tangyuanAI.tracing import (
    ConsoleExporter,
    JSONLExporter,
    Span,
    SpanKind,
    Trace,
    Tracer,
    set_default_tracer,
    trace_fc_round,
    trace_llm_call,
    trace_tool_call,
)


def test_span_finish_computes_latency():
    s = Span(span_id="s1", trace_id="t1", parent_id=None, name="x", kind=SpanKind.LLM)
    assert s.latency_ms is None
    s.finish()
    assert s.latency_ms is not None
    assert s.latency_ms >= 0


def test_span_set_attr_and_error():
    s = Span(span_id="s1", trace_id="t1", parent_id=None, name="x", kind=SpanKind.LLM)
    s.set_attr("model", "gpt-5")
    s.set_error("boom")
    assert s.attrs["model"] == "gpt-5"
    assert s.status == "error"
    assert s.error == "boom"


def test_tracer_start_trace_emits_root_span():
    tracer = Tracer(exporter=None)
    trace = tracer.start_trace("agent.run", attrs={"k": "v"})
    assert trace.name == "agent.run"
    assert trace.root_span_id is not None
    tracer.end_trace(trace)


def test_span_context_managers_emit_spans():
    """三个 context manager 各自创建一个 span 并通过 tracer 注册。"""
    captured = []

    class CapturingExporter:
        def export(self, trace):
            captured.append(trace)

    tracer = Tracer(exporter=CapturingExporter())
    set_default_tracer(tracer)
    trace = tracer.start_trace("agent.run")

    with trace_llm_call(model="gpt-5") as llm_span:
        llm_span.set_attr("latency_ms", 120)
        with trace_tool_call(tool_name="get_weather"):
            with trace_fc_round(round_index=0):
                pass

    tracer.end_trace(trace)
    assert len(captured) == 1
    kinds = [s.kind for s in captured[0].spans]
    assert SpanKind.LLM in kinds
    assert SpanKind.TOOL in kinds
    assert SpanKind.FC_ROUND in kinds


def test_console_exporter_writes_log(caplog):
    exporter = ConsoleExporter()
    trace = Trace(trace_id="abc", name="test")
    span = Span(span_id="s1", trace_id="abc", parent_id=None, name="sub", kind=SpanKind.LLM)
    span.set_attr("model", "gpt-5")
    span.finish()
    trace.spans.append(span)
    trace.finish()

    import logging as _logging
    _logger = _logging.getLogger("tangyuanAI.tracing")
    _logger.setLevel(_logging.DEBUG)
    with caplog.at_level(_logging.DEBUG, logger="tangyuanAI.tracing"):
        exporter.export(trace)
    # Console exporter 输出 [trace] + span 行
    msgs = [r.message for r in caplog.records]
    assert any("[trace]" in m and "test" in m for m in msgs)
    assert any("sub" in m for m in msgs)


def test_jsonl_exporter_writes_one_line_per_span(tmp_path):
    path = tmp_path / "spans.jsonl"
    exporter = JSONLExporter(str(path))
    trace = Trace(trace_id="abc", name="jsonl-test")
    span = Span(span_id="s1", trace_id="abc", parent_id=None, name="x", kind=SpanKind.LLM)
    span.set_attr("k", 1)
    span.finish()
    trace.spans.append(span)
    exporter.export(trace)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["trace_id"] == "abc"
    assert rec["name"] == "x"
    assert rec["kind"] == "llm"
    assert rec["attrs"]["k"] == 1


def test_default_tracer_singleton():
    from tangyuanAI.tracing import get_default_tracer
    t1 = get_default_tracer()
    t2 = get_default_tracer()
    assert t1 is t2
