"""sandbox.py 单元测试。"""
from __future__ import annotations

from tangyuanAI.sandbox import NullSandbox, Sandbox, SandboxError, default_sandbox


def test_default_sandbox_is_null():
    sb = default_sandbox()
    assert isinstance(sb, NullSandbox)


def test_null_sandbox_before_returns_true():
    sb = NullSandbox()
    assert sb.before(lambda: None, {"x": 1}) is True


def test_null_sandbox_after_passes_through():
    sb = NullSandbox()
    sentinel = object()
    assert sb.after(lambda: None, {"x": 1}, sentinel) is sentinel


def test_null_sandbox_error_is_noop():
    sb = NullSandbox()
    # should not raise
    sb.error(lambda: None, {"x": 1}, ValueError("boom"))


def test_sandbox_is_abstract():
    """Sandbox 是抽象基类,直接实例化应失败。"""
    import pytest
    with pytest.raises(TypeError):
        Sandbox()  # type: ignore[abstract]


def test_sandbox_error_inherits_permission_error():
    assert issubclass(SandboxError, PermissionError)