"""tangyuanAI sandbox hook —— v1.4.0 引入的工具执行沙箱接入点。

设计目标:
- 预留接口,默认 NullSandbox(no-op,行为不变)
- 实际 sandboxer 实现(subprocess / docker / wasm)留给后续 PR
- API 表面经过 `security-review` skill 审查,确保无法绕过 ACL
- 用户必须显式 `agent.register_sandbox(my_sandbox)` 才能替换默认
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class Sandbox(ABC):
    """工具执行沙箱抽象。"""

    @abstractmethod
    def before(self, func: Callable, args: dict[str, Any]) -> bool:
        """工具执行前调用。

        返回 True 允许执行,False 拒绝。
        可抛出 `PermissionError` / `TimeoutError` 等异常让框架走错误路径。
        """
        raise NotImplementedError

    @abstractmethod
    def after(self, func: Callable, args: dict[str, Any], result: Any) -> Any:
        """工具执行后调用。可修改 / 校验 / 记录结果。

        返回值即为工具最终返回给 LLM 的结果。
        """
        raise NotImplementedError

    @abstractmethod
    def error(self, func: Callable, args: dict[str, Any], exc: BaseException) -> None:
        """工具执行异常时调用。可记录 / 上报 / 重新抛。"""
        raise NotImplementedError


class NullSandbox(Sandbox):
    """默认 sandbox。什么也不做。行为与 v1.3.0 一致。"""

    def before(self, func, args):
        return True

    def after(self, func, args, result):
        return result

    def error(self, func, args, exc):
        return None


_DEFAULT_SANDBOX = NullSandbox()


def default_sandbox() -> Sandbox:
    """返回当前默认 sandbox(总是 NullSandbox,直到有非默认 sandboxer 实现)。"""
    return _DEFAULT_SANDBOX


class SandboxError(PermissionError):
    """sandbox.before 拒绝时的异常。框架捕获后会作为 tool_result_invalid 注入 history。"""
    pass
