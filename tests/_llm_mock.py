# -*- coding: utf-8 -*-
"""⚠️ TEST-ONLY UTILITY — 不属于 tangyuanAI 公共 API。

LLM 协议层 mock —— OpenAI 兼容 Chat Completions + Anthropic Messages API。

仅供 ``tangyuanAI/tests/`` 下的单测使用；不是发布给用户的 SDK 的一部分。
文件名前缀 ``_`` 配合目录隔离，确保不会被外部代码意外 import。

设计目标：让 Agent 走完整 wire 协议（构造 payload → 序列化 → 序列化回来），
所以 mock 不是返回硬编码结构，而是把"响应工厂"装到队列里，每个请求消耗一个；
mock 内部按请求里的 ``stream`` 字段决定返回 JSON 还是 SSE。

支持的能力：

- OpenAI：非流式 JSON + 流式 SSE（chunk.choices[].delta.content / tool_calls）
- Anthropic：非流式 JSON（content blocks）+ 流式 SSE（message_start / content_block_* / message_delta / message_stop）
- 多轮：每条请求消耗队列里一个响应工厂，工厂拿到原始 request body（可看 LLM 上轮发了什么）
- 校验：跑完测试可以断言 "调了几次" / "每次请求的 tools / messages 是什么"

不开真实 LLM、不依赖网络。
"""
from __future__ import annotations

import json
import threading
import time
import uuid as _uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, List, Optional

__all__ = [
    # 响应工厂
    "anthropic_text_response",
    "anthropic_tool_use_response",
    "anthropic_text_then_tool_response",
    "openai_text_response",
    "openai_tool_call_response",
    # 状态 + handler + 启动器
    "MockState",
    "_AnthropicMockHandler",
    "_OpenAIMockHandler",
    "_start_mock_server",
]


# ===========================================================================
# 响应工厂：构造 Anthropic / OpenAI 的标准响应 dict
# ===========================================================================

def anthropic_text_response(text: str, stop_reason: str = "end_turn") -> dict:
    """Anthropic：纯文本响应"""
    return {
        "id": f"msg-{_uuid.uuid4().hex[:8]}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "model": "test-model",
        "stop_reason": stop_reason,
        "usage": {"input_tokens": 5, "output_tokens": len(text)},
    }


def anthropic_tool_use_response(
    tool_id: str, tool_name: str, tool_input: dict, stop_reason: str = "tool_use"
) -> dict:
    """Anthropic：tool_use 响应（无前置文本）"""
    return {
        "id": f"msg-{_uuid.uuid4().hex[:8]}",
        "type": "message",
        "role": "assistant",
        "content": [
            {"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input}
        ],
        "model": "test-model",
        "stop_reason": stop_reason,
        "usage": {"input_tokens": 5, "output_tokens": 10},
    }


def anthropic_text_then_tool_response(
    text: str, tool_id: str, tool_name: str, tool_input: dict
) -> dict:
    """Anthropic：先文本后 tool_use 的混合响应"""
    return {
        "id": f"msg-{_uuid.uuid4().hex[:8]}",
        "type": "message",
        "role": "assistant",
        "content": [
            {"type": "text", "text": text},
            {"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input},
        ],
        "model": "test-model",
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 5, "output_tokens": 20},
    }


def openai_text_response(text: str, finish_reason: str = "stop") -> dict:
    """OpenAI：纯文本响应（非流式 chat.completion）"""
    return {
        "id": f"chatcmpl-{_uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": len(text), "total_tokens": 5 + len(text)},
    }


def openai_tool_call_response(
    tool_id: str, tool_name: str, arguments: dict, finish_reason: str = "tool_calls"
) -> dict:
    """OpenAI：tool_calls 响应"""
    return {
        "id": f"chatcmpl-{_uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tool_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                            },
                        }
                    ],
                },
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
    }


# ===========================================================================
# SSE 事件序列化：把 JSON 响应拆成 Anthropic / OpenAI 的事件流
# ===========================================================================

def _anthropic_dict_to_sse_events(data: dict) -> List[dict]:
    """Anthropic JSON 响应 → SSE 事件序列。

    text 块按字符切 delta；tool_use 块把 input 整体作为 input_json_delta。
    """
    events: List[dict] = []
    msg_id = data.get("id", "msg-test")
    model = data.get("model", "test-model")
    start_usage = {"input_tokens": 5, "output_tokens": 0}
    final_usage = data.get("usage", start_usage)

    events.append({
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "usage": start_usage,
        },
    })

    for i, block in enumerate(data.get("content", [])):
        btype = block.get("type")
        if btype == "text":
            events.append({
                "type": "content_block_start",
                "index": i,
                "content_block": {"type": "text", "text": ""},
            })
            text = block.get("text", "")
            for ch in text:
                events.append({
                    "type": "content_block_delta",
                    "index": i,
                    "delta": {"type": "text_delta", "text": ch},
                })
            events.append({"type": "content_block_stop", "index": i})
        elif btype == "tool_use":
            events.append({
                "type": "content_block_start",
                "index": i,
                "content_block": {
                    "type": "tool_use",
                    "id": block.get("id", "toolu_test"),
                    "name": block.get("name", ""),
                    "input": {},
                },
            })
            input_json = json.dumps(block.get("input", {}), ensure_ascii=False)
            events.append({
                "type": "content_block_delta",
                "index": i,
                "delta": {"type": "input_json_delta", "partial_json": input_json},
            })
            events.append({"type": "content_block_stop", "index": i})

    events.append({
        "type": "message_delta",
        "delta": {"stop_reason": data.get("stop_reason", "end_turn")},
        "usage": final_usage,
    })
    events.append({"type": "message_stop"})
    return events


def _openai_dict_to_sse_chunks(data: dict) -> List[dict]:
    """OpenAI JSON 响应 → SSE chunk 序列。"""
    chunks: List[dict] = []
    created = int(time.time())
    base = {"id": "chatcmpl-test", "object": "chat.completion.chunk",
            "created": created, "model": "test-model"}
    choices = data.get("choices", [])
    if not choices:
        return chunks
    msg = choices[0].get("message", {})

    # role + 空 content 起手
    chunks.append({
        **base,
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""},
                     "finish_reason": None}],
    })
    # content 按字符切
    content = msg.get("content") or ""
    for ch in content:
        chunks.append({
            **base,
            "choices": [{"index": 0, "delta": {"content": ch},
                         "finish_reason": None}],
        })
    # tool_calls 整段切（实际 API 也是分段，但测试不强求）
    tool_calls = msg.get("tool_calls") or []
    for j, tc in enumerate(tool_calls):
        chunks.append({
            **base,
            "choices": [{
                "index": 0,
                "delta": {"tool_calls": [{
                    "index": j,
                    "id": tc.get("id"),
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                }]},
                "finish_reason": None,
            }],
        })
    # 收尾
    chunks.append({
        **base,
        "choices": [{"index": 0, "delta": {},
                     "finish_reason": choices[0].get("finish_reason", "stop")}],
    })
    return chunks


# ===========================================================================
# Mock HTTP servers
# ===========================================================================

@dataclass
class MockState:
    """Mock 状态：响应队列 + 调用记录。多线程安全（lock 保护）。"""
    response_script: List[Callable[[dict], dict]] = field(default_factory=list)
    request_log: List[dict] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    call_count: int = 0
    # 非 ping 请求（model=max_tokens==1 ping 跳过计数）
    real_call_count: int = 0

    def queue(self, factory: Callable[[dict], dict]) -> None:
        with self.lock:
            self.response_script.append(factory)

    def pop(self, body: dict) -> dict:
        with self.lock:
            self.request_log.append(body)
            self.call_count += 1
            # max_tokens=1 + 单字符 ping = 探测请求，不计 real_call
            if not (body.get("max_tokens") == 1 and body.get("messages") == [{"role": "user", "content": "ping"}]):
                self.real_call_count += 1
            if not self.response_script:
                raise RuntimeError(
                    f"mock script empty (call #{self.call_count}, body keys={list(body.keys())})"
                )
            return self.response_script.pop(0)(body)


class _AnthropicMockHandler(BaseHTTPRequestHandler):
    state: Optional[MockState] = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {}
        is_stream = bool(body.get("stream"))

        # _connectivity 探测请求（max_tokens=1 单轮 ping）不消耗队列；
        # 直接返回最小合法响应，让后台线程立刻退出。
        is_ping = (
            body.get("max_tokens") == 1
            and isinstance(body.get("messages"), list)
            and len(body["messages"]) == 1
        )
        if is_ping:
            self._send_json({
                "id": "msg-ping", "type": "message", "role": "assistant",
                "content": [], "model": "test-model", "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 0},
            })
            return

        try:
            data = self.state.pop(body)
        except RuntimeError as e:
            self.send_error(500, str(e))
            return

        if is_stream:
            self._send_sse(_anthropic_dict_to_sse_events(data))
        else:
            self._send_json(data)

    def _send_json(self, data: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _send_sse(self, events: List[dict]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for ev in events:
            self.wfile.write(f"event: {ev['type']}\n".encode())
            self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()

    def log_message(self, *_args, **_kwargs):  # noqa: D401 - 静默
        pass


class _OpenAIMockHandler(BaseHTTPRequestHandler):
    state: Optional[MockState] = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {}
        is_stream = bool(body.get("stream"))

        # 探测请求短路：BaseAgent.Connectivity 启动时发 max_tokens=1 单轮 ping
        is_ping = (
            body.get("max_tokens") == 1
            and isinstance(body.get("messages"), list)
            and len(body["messages"]) == 1
        )
        if is_ping:
            self._send_json({
                "id": "ping", "object": "chat.completion", "created": int(time.time()),
                "model": "test-model",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": ""},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1},
            })
            return

        try:
            data = self.state.pop(body)
        except RuntimeError as e:
            self.send_error(500, str(e))
            return

        if is_stream:
            self._send_sse(_openai_dict_to_sse_chunks(data))
        else:
            self._send_json(data)

    def _send_json(self, data: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _send_sse(self, chunks: List[dict]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for ch in chunks:
            self.wfile.write(f"data: {json.dumps(ch, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *_args, **_kwargs):  # noqa: D401 - 静默
        pass


def _start_mock_server(handler_cls: type) -> tuple[str, ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return base, server
