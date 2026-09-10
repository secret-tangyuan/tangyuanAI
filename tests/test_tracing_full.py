"""tracing 完整测试 — PR-11 (CostCalculator + JSONLExporter 完整实现 + OpenTelemetryExporter stub)。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from tangyuanAI.tracing import (
    CostCalculator,
    JSONLExporter,
    Span,
    SpanKind,
    Trace,
    Tracer,
    register_pricing,
)


def test_cost_calculator_known_model_exact_match():
    cost, est = CostCalculator.estimate("gpt-4o", 1_000_000, 1_000_000)
    assert est is True
    # gpt-4o: 2.50/1M prompt + 10.00/1M completion
    assert cost == pytest.approx(12.50)


def test_cost_calculator_known_model_case_insensitive():
    cost, est = CostCalculator.estimate("GPT-4O", 1_000, 500)
    assert est is True
    assert cost > 0


def test_cost_calculator_known_model_with_version_suffix():
    """gpt-5-0613 也应该匹配 gpt-5。"""
    cost, est = CostCalculator.estimate("gpt-5-0613", 1_000_000, 0)
    assert est is True
    # gpt-5: 1.25/1M prompt
    assert cost == pytest.approx(1.25)


def test_cost_calculator_unknown_model_returns_zero():
    cost, est = CostCalculator.estimate("unknown-future-model-9000", 1000, 500)
    assert cost == 0.0
    assert est is False


def test_cost_calculator_anthropic():
    cost, est = CostCalculator.estimate("claude-3-5-sonnet-latest", 1_000_000, 1_000_000)
    assert est is True
    # 3.00/1M prompt + 15.00/1M completion
    assert cost == pytest.approx(18.00)


def test_cost_calculator_register_pricing_runtime():
    register_pricing("custom-model-1", 0.5, 2.0)
    cost, est = CostCalculator.estimate("custom-model-1", 1_000_000, 1_000_000)
    assert est is True
    assert cost == pytest.approx(2.5)


def test_cost_calculator_add_to_span_populates_attrs():
    span = Span(span_id="s1", trace_id="t1", parent_id=None, name="llm", kind=SpanKind.LLM)
    CostCalculator.add_to_span(span, "gpt-4o-mini", 100_000, 50_000)
    assert span.attrs["model"] == "gpt-4o-mini"
    assert span.attrs["prompt_tokens"] == 100_000
    assert span.attrs["completion_tokens"] == 50_000
    assert span.attrs["cost_estimated"] is True
    # 0.15/1M * 0.1 + 0.60/1M * 0.05 = 0.015 + 0.030 = 0.045
    assert span.attrs["cost_usd"] == pytest.approx(0.045, rel=1e-3)


def test_jsonl_exporter_full_serialization(tmp_path):
    path = tmp_path / "traces.jsonl"
    exporter = JSONLExporter(str(path))
    trace = Trace(trace_id="full-test", name="agent.run")
    parent = Span(
        span_id="p1", trace_id="full-test", parent_id=None,
        name="agent.run", kind=SpanKind.AGENT,
    )
    parent.set_attr("agent_name", "test")
    parent.finish()
    trace.spans.append(parent)
    child = Span(
        span_id="c1", trace_id="full-test", parent_id="p1",
        name="llm.chat", kind=SpanKind.LLM,
    )
    child.set_attr("model", "gpt-4o")
    child.set_attr("prompt_tokens", 100)
    child.set_attr("completion_tokens", 50)
    child.set_attr("cost_usd", 0.00075)
    child.set_attr("cost_estimated", True)
    child.finish()
    trace.spans.append(child)
    trace.finish()
    exporter.export(trace)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    recs = [json.loads(l) for line in lines]
    assert recs[0]["name"] == "agent.run"
    assert recs[0]["attrs"]["agent_name"] == "test"
    assert recs[1]["parent_id"] == "p1"
    assert recs[1]["attrs"]["model"] == "gpt-4o"
    assert recs[1]["attrs"]["cost_usd"] == pytest.approx(0.00075)


def test_tracer_with_jsonl_exporter_roundtrip(tmp_path):
    """完整 trace 生命周期:start -> 3 spans -> end -> JSONL 文件可读"""
    from tangyuanAI.tracing import trace_llm_call
    path = tmp_path / "out.jsonl"
    tracer = Tracer(exporter=JSONLExporter(str(path)))
    trace = tracer.start_trace("agent.run")

    with trace_llm_call(name="llm", stream=False) as llm_span:
        llm_span.set_attr("model", "gpt-4o")
        llm_span.set_attr("prompt_tokens", 200)
        llm_span.set_attr("completion_tokens", 100)

    tracer.end_trace(trace)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    rec = json.loads(lines[0])
    assert rec["name"] == "llm"
    assert rec["attrs"]["prompt_tokens"] == 200


def test_cli_trace_subcommand_registered():
    """cli.py 应该注册 tangyuanai trace 子命令。"""
    from tangyuanAI import cli as cli_mod
    parser = cli_mod._build_parser()
    # argparse.Namespace dest 会有 cmd
    help_text = parser.format_help()
    assert "trace" in help_text


def test_cli_trace_last_prints_no_file_friendly(capsys):
    """tangyuanai trace last 在 logs/spans.jsonl 不存在时打印友好提示。"""
    from tangyuanAI import cli as cli_mod
    # 在空 cwd 中跑
    old_cwd = os.getcwd()
    try:
        os.chdir(os.path.dirname(cli_mod.__file__))
        # 删 spans.jsonl 临时测试
        log_path = Path("logs/spans.jsonl")
        existed = log_path.exists()
        if existed:
            log_path.rename(log_path.with_suffix(".jsonl.bak"))
        try:
            args = cli_mod._build_parser().parse_args(["trace", "last"])
            assert args.func is cli_mod.cmd_trace_last
            rc = args.func(args)
            captured = capsys.readouterr()
            assert rc == 1
            assert "未找到" in captured.out or "未找到" in captured.err
        finally:
            if log_path.with_suffix(".jsonl.bak").exists():
                log_path.with_suffix(".jsonl.bak").rename(log_path)
    finally:
        os.chdir(old_cwd)
