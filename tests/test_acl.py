# -*- coding: utf-8 -*-
"""
工具 ACL（访问控制）单测。

覆盖：

- ``allowed_agents`` 用 agent name 不用 uuid（这是 v0.3.0 文档约定）
- agent 调没权限的工具 → 框架返回"找不到"
- agent_list[uuid] 名字映射正确（uuid → name 翻译在 check_permission 内）
- ACL 拒绝的端到端：用户让 agent 调危险工具 → 框架阻断 → LLM 道歉

真实任务：用户让 agent 调一个 admin-only 的工具 → agent 没权限。
"""
from __future__ import annotations

import uuid as _uuid

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
    agent_template_pool,
    template_agent,
    tool_registry,
)
from tangyuanAI.anthropic_agent import AnthropicAgent


@pytest.fixture(autouse=True)
def _clean_globals():
    saved_tools = dict(tool_registry._tools)
    saved_perms = dict(tool_registry._agent_permissions)
    agent_list.clear()
    agent_template_pool.clear()
    yield
    agent_list.clear()
    agent_template_pool.clear()
    tool_registry._tools.clear()
    tool_registry._agent_permissions.clear()
    tool_registry._tools.update(saved_tools)
    tool_registry._agent_permissions.update(saved_perms)


def _start_mock():
    state = MockState()
    _AnthropicMockHandler.state = state
    base_url, server = _start_mock_server(_AnthropicMockHandler)
    return state, base_url, server


def _make_agent(name: str, base_url: str) -> AnthropicAgent:
    @template_agent(name, uuid=_uuid.uuid4().hex, description="test")
    class _A(Agent):
        protocol = "anthropic"
        prompt = "x"
        model_name = "m"
        api_key = "k"
        api_provider = base_url
    activate_template(name)
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001
    return inst


# ===========================================================================
# 单元级：check_permission 行为
# ===========================================================================

def test_allowed_agents_uses_agent_name_not_uuid():
    """check_permission 内部做 uuid→name 翻译，所以 allowed_agents 必须传 name。

    场景：
    - 工具 allowed_agents 传 name（正确）→ 任何 agent 用 uuid 调都先被翻译成 name 再比对
    - 工具 allowed_agents 传 uuid（错误用法）→ 翻译后是 name，name 不在 [uuid] 里 → False
    """
    # 真实任务：先注册一个 agent 拿到合法 uuid
    @template_agent("acl-test", uuid=_uuid.uuid4().hex, description="test")
    class _A(AnthropicAgent):
        protocol = "anthropic"
        prompt = "x"
        model_name = "m"
        api_key = "k"
        api_provider = "http://x"

    activate_template("acl-test")
    real_agent_uuid = agent_list["acl-test"].uuid  # 实际 uuid
    real_agent_name = "acl-test"  # 实际 name

    @tool_registry.register_tool(
        allowed_agents=[real_agent_name],  # ✓ 正确：传 name
        name="tool-for-acl-test",
        description="x",
        parameters={"type": "object", "properties": {}},
    )
    def tool_for_acl_test() -> str:
        return "x"

    # 用 agent 的 uuid 调 → 翻译成 name → name 在 allowed 里 → True
    assert tool_registry.check_permission(real_agent_uuid, "tool-for-acl-test") is True
    # 用 agent 的 name 调 → True
    assert tool_registry.check_permission(real_agent_name, "tool-for-acl-test") is True
    # 用一个**其他** uuid/name（既不是这个 agent 的也不是翻译目标）→ False
    assert tool_registry.check_permission("other-uuid", "tool-for-acl-test") is False


def test_allowed_agents_with_uuid_in_list_fails_legacy_pattern():
    """场景：用户误用 allowed_agents 传了 uuid（老项目代码）→ 不在 allowed 里 → False。
    推荐用 name（v0.3.0+ 文档约定）。
    """
    @template_agent("acl-uuid", uuid=_uuid.uuid4().hex, description="test")
    class _A(AnthropicAgent):
        protocol = "anthropic"
        prompt = "x"
        model_name = "m"
        api_key = "k"
        api_provider = "http://x"

    activate_template("acl-uuid")
    real_uuid = agent_list["acl-uuid"].uuid

    @tool_registry.register_tool(
        allowed_agents=[real_uuid],  # 误用：传 uuid 而不是 name
        name="legacy-tool",
        description="x",
        parameters={"type": "object", "properties": {}},
    )
    def legacy_tool() -> str:
        return "x"

    # 调 check_permission(real_uuid, ...) → uuid 翻译成 name → name 不在 [uuid] → False
    assert tool_registry.check_permission(real_uuid, "legacy-tool") is False


def test_check_permission_uuid_resolves_to_name():
    """check_permission 接受 agent uuid，内部翻译成 name 再比对。"""
    uuid_str = _uuid.uuid4().hex

    @template_agent("my-named-agent", uuid=uuid_str, description="test")
    class _A(Agent):
        protocol = "anthropic"
        prompt = "x"
        model_name = "m"
        api_key = "k"
        api_provider = "http://x"

    activate_template("my-named-agent")

    @tool_registry.register_tool(
        allowed_agents=["my-named-agent"],
        name="my-tool",
        description="x",
        parameters={"type": "object", "properties": {}},
    )
    def my_tool() -> str:
        return "x"

    # 用 uuid 调 check_permission → 内部翻译成 name → 比对成功
    assert tool_registry.check_permission(uuid_str, "my-tool") is True
    # 用 name 调也 OK
    assert tool_registry.check_permission("my-named-agent", "my-tool") is True
    # 用错误的 uuid/name → False
    assert tool_registry.check_permission("other-uuid", "my-tool") is False
    assert tool_registry.check_permission("other-name", "my-tool") is False


def test_check_permission_none_means_global():
    """allowed_agents=None → 任何 agent 都能调"""
    @tool_registry.register_tool(
        allowed_agents=None,
        name="global",
        description="x",
        parameters={"type": "object", "properties": {}},
    )
    def global_fn() -> str:
        return "x"

    assert tool_registry.check_permission("any-uuid", "global") is True
    assert tool_registry.check_permission("any-name", "global") is True


def test_check_permission_unknown_tool_returns_false():
    """工具未注册 → False"""
    assert tool_registry.check_permission("any", "nonexistent-tool") is False


# ===========================================================================
# 端到端：用户让 agent 调受限工具
# ===========================================================================

def test_user_asks_agent_to_run_admin_only_tool_agent_denies():
    """场景：用户让普通 agent 跑 admin-only 的删库工具。
    真实任务："请帮我删库" → agent 想调 delete_database → ACL 阻断 → LLM 道歉。
    """
    state, base_url, server = _start_mock()
    try:
        agent = _make_agent("regular-user", base_url)

        @tool_registry.register_tool(
            allowed_agents=["admin"],
            name="delete_database",
            description="删库（高危）",
            parameters={"type": "object", "properties": {}, "required": []},
        )
        def delete_database() -> str:
            return "数据库已删除"  # 关键：永远不应被 LLM 看到

        # mock: LLM 调 delete_database（无权限） → 收到"找不到" → 道歉
        state.queue(lambda _b: anthropic_tool_use_response(
            "dangerous", "delete_database", {},
        ))
        state.queue(lambda _b: anthropic_text_response(
            "抱歉，我没有权限执行删库操作。",
        ))

        out = agent.conversation("请帮我删库")
        # 关键断言：delete_database 的实际内容"数据库已删除"绝不能出现
        assert "数据库已删除" not in out
        # LLM 道歉了
        assert "权限" in out or "抱歉" in out
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


def test_user_asks_agent_to_call_own_tool_succeeds():
    """对照：让 agent 调自己有权调的工具 → 正常返回"""
    state, base_url, server = _start_mock()
    try:
        agent = _make_agent("trusted-user", base_url)

        @tool_registry.register_tool(
            allowed_agents=["trusted-user"],
            name="read_file",
            description="读文件",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        )
        def read_file(path: str) -> str:
            return f"contents of {path}"

        state.queue(lambda _b: anthropic_tool_use_response(
            "f1", "read_file", {"path": "/tmp/x.txt"},
        ))
        state.queue(lambda _b: anthropic_text_response("文件内容：contents of /tmp/x.txt"))

        out = agent.conversation("读 /tmp/x.txt")
        assert "contents of /tmp/x.txt" in out
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None
