"""tangyuanAI tracing —— v1.4.0 引入的轻量级 span / trace 框架。

设计目标:
- 零依赖(PR-8 骨架)
- 默认无侵入开启(每个 LLM call / tool call 自动套)
- 可被 OpenTelemetry / JSONL 替代(PR-10 扩展)
- 不依赖全局状态,通过 contextvar 隔离 trace

PR-8 状态:
- Trace / Span / SpanKind dataclass
- start_trace / end_trace / current_trace API
- 6 处默认 hook(transport.chat / achat / chat_stream / achat_stream × 各 2 类协议)
- ConsoleExporter(默认 stderr)
- JSONLExporter / OpenTelemetryExporter 在 PR-10 加
"""
from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

_logger = logging.getLogger(__name__)


class SpanKind(str, Enum):
    LLM = "llm"
    TOOL = "tool"
    AGENT = "agent"
    FC_ROUND = "fc_round"
    SANDBOX = "sandbox"


@dataclass
class Span:
    span_id: str
    trace_id: str
    parent_id: Optional[str]
    name: str
    kind: SpanKind
    start_ms: float = field(default_factory=lambda: time.time() * 1000)
    end_ms: Optional[float] = None
    latency_ms: Optional[float] = None
    attrs: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"  # "ok" | "error"
    error: Optional[str] = None

    def set_attr(self, key: str, value: Any) -> None:
        self.attrs[key] = value

    def set_error(self, msg: str) -> None:
        self.status = "error"
        self.error = msg

    def finish(self) -> None:
        if self.end_ms is not None:
            return
        self.end_ms = time.time() * 1000
        self.latency_ms = self.end_ms - self.start_ms


@dataclass
class Trace:
    trace_id: str
    name: str
    started_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    spans: list[Span] = field(default_factory=list)
    root_span_id: Optional[str] = None
    finished_at_ms: Optional[float] = None

    def finish(self) -> None:
        if self.finished_at_ms is not None:
            return
        self.finished_at_ms = time.time() * 1000


_current_trace: ContextVar[Optional[Trace]] = ContextVar("tangyuan_current_trace", default=None)
_current_span: ContextVar[Optional[Span]] = ContextVar("tangyuan_current_span", default=None)


def current_trace() -> Optional[Trace]:
    return _current_trace.get()


def current_span() -> Optional[Span]:
    return _current_span.get()


class Tracer:
    """tracing 主入口。每个 agent 类 / 全局可选配一个。"""

    def __init__(self, exporter: Optional["SpanExporter"] = None, sample_rate: float = 1.0):
        self.exporter: SpanExporter = exporter or ConsoleExporter()
        self.sample_rate = max(0.0, min(1.0, sample_rate))

    def start_trace(self, name: str, attrs: Optional[dict] = None) -> Trace:
        trace = Trace(trace_id=uuid.uuid4().hex, name=name)
        if attrs:
            root = self._start_span(name=name, kind=SpanKind.AGENT, trace=trace, attrs=attrs)
            trace.root_span_id = root.span_id
        _current_trace.set(trace)
        return trace

    def end_trace(self, trace: Trace) -> None:
        trace.finish()
        for span in trace.spans:
            if span.end_ms is None:
                span.finish()
        if self.exporter:
            self.exporter.export(trace)
        if _current_trace.get() is trace:
            _current_trace.set(None)
            _current_span.set(None)

    def _start_span(
        self,
        name: str,
        kind: SpanKind,
        trace: Optional[Trace] = None,
        attrs: Optional[dict] = None,
    ) -> Span:
        if trace is None:
            trace = _current_trace.get()
            if trace is None:
                trace = self.start_trace(name="auto")
        parent = _current_span.get()
        span = Span(
            span_id=uuid.uuid4().hex,
            trace_id=trace.trace_id,
            parent_id=parent.span_id if parent else None,
            name=name,
            kind=kind,
            attrs=attrs or {},
        )
        trace.spans.append(span)
        _current_span.set(span)
        return span

    def _finish_span(self, span: Span) -> None:
        span.finish()
        if _current_span.get() is span:
            # 恢复 parent (栈式 pop)
            for s in reversed(_current_trace.get().spans if _current_trace.get() else []):
                if s.span_id == span.parent_id:
                    _current_span.set(s)
                    return
            _current_span.set(None)


_default_tracer: Optional[Tracer] = None


def get_default_tracer() -> Tracer:
    """获取默认 tracer。第一次调用时构造,后续复用。"""
    global _default_tracer
    if _default_tracer is None:
        _default_tracer = Tracer()
    return _default_tracer


def set_default_tracer(tracer: Tracer) -> None:
    """覆盖默认 tracer。给 production 切 OpenTelemetry 时用。"""
    global _default_tracer
    _default_tracer = tracer


def trace_llm_call(name: str = "llm.call", **attrs) -> "SpanContext":
    """作为 context manager 使用:

    with trace_llm_call(model="gpt-5"):
        response = transport.chat(req)
    """
    return SpanContext(kind=SpanKind.LLM, name=name, attrs=attrs)


def trace_tool_call(name: str = "tool.call", **attrs) -> "SpanContext":
    return SpanContext(kind=SpanKind.TOOL, name=name, attrs=attrs)


def trace_fc_round(name: str = "fc.round", **attrs) -> "SpanContext":
    return SpanContext(kind=SpanKind.FC_ROUND, name=name, attrs=attrs)


class SpanContext:
    """轻量级 context manager: `with trace_llm_call(...) as span: ...`"""

    def __init__(self, kind: SpanKind, name: str, attrs: Optional[dict] = None):
        self.tracer = get_default_tracer()
        self.kind = kind
        self.name = name
        self.attrs = attrs or {}
        self.span: Optional[Span] = None
        self._token: Any = None

    def __enter__(self) -> Span:
        self.span = self.tracer._start_span(name=self.name, kind=self.kind, attrs=self.attrs)
        self._token = _current_span.set(self.span)
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.span.set_error(f"{exc_type.__name__}: {exc_val}")
        self.tracer._finish_span(self.span)
        _current_span.reset(self._token)


# ============================================================
# Exporters
# ============================================================


class SpanExporter:
    """span 导出器抽象。"""

    def export(self, trace: Trace) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class ConsoleExporter(SpanExporter):
    """人类可读的 stderr 输出,默认。"""

    def export(self, trace: Trace) -> None:
        duration_ms = (
            (trace.finished_at_ms or time.time() * 1000) - trace.started_at_ms
        )
        _logger.info(
            f"[trace] {trace.name} trace_id={trace.trace_id[:8]} "
            f"spans={len(trace.spans)} duration_ms={duration_ms:.1f}"
        )
        for span in trace.spans:
            attr_str = ", ".join(
                f"{k}={v}" for k, v in span.attrs.items()
            )
            latency = f"{span.latency_ms:.1f}" if span.latency_ms is not None else "?"
            _logger.debug(
                f"  span={span.name} kind={span.kind.value} "
                f"latency_ms={latency} status={span.status} {attr_str}"
            )


class JSONLExporter(SpanExporter):
    """每行一条 span,写到 `logs/spans.jsonl`。PR-10 完整实现,这里只占位。"""

    def __init__(self, path: str = "logs/spans.jsonl"):
        self.path = path

    def export(self, trace: Trace) -> None:
        # PR-10 实现完整 JSONL 序列化
        # 现在只是 stub,确保 API 完整
        import json
        import os
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            for span in trace.spans:
                f.write(
                    json.dumps(
                        {
                            "trace_id": span.trace_id,
                            "span_id": span.span_id,
                            "parent_id": span.parent_id,
                            "name": span.name,
                            "kind": span.kind.value,
                            "start_ms": span.start_ms,
                            "end_ms": span.end_ms,
                            "latency_ms": span.latency_ms,
                            "status": span.status,
                            "error": span.error,
                            "attrs": span.attrs,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
