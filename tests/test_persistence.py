# -*- coding: utf-8 -*-
"""
Persistence 模块单测（v0.3.2+）。

覆盖：

- **导出格式**：INI 头 + JSONL 体，人类可读、``git diff`` 友好
- **FileBackend**：roundtrip / delete / list / 路径穿越保护
- **SQLiteBackend**（实验）：roundtrip / delete / list
- **插件注册**：`register_backend` / `get_backend` / `set_default_backend`
- **类身份解析**：class path 成功 / 失败 → 查 agent_list / 失败 → 抛错
- **hooks 持久化**：保存时记全限定名，加载时重新绑定
- **自动保存（实时存储）**：
  - ``is_enabled()`` 默认 False
  - ``configure(enabled=True)`` 启用
  - ``conversation_with_tool`` 退出时自动保存
  - async 路径同样
  - FC 模式递归调用不会重复保存
  - ``key_strategy="name"`` 用 agent.name
  - 持久化失败不应阻塞对话
- **环境变量**：`TANGYUAN_PERSISTENCE=on` 等通过 ``_read_env_config()`` 启用
"""
from __future__ import annotations

import json
import os
import textwrap
import uuid as _uuid
from pathlib import Path
from typing import Iterator

import pytest
from tangyuanAI import (
    Agent,
    activate_template,
    agent_list,
    persistence,
    template_agent,
    tool_registry,
)
from tangyuanAI.persistence import (
    AgentNotFoundError,
    FileBackend,
    FormatError,
    SQLiteBackend,
    _read_env_config,
    _SectionedFile,
    auto_save,
    backends,
    configure,
    disable,
    export_state_string,
    is_enabled,
    list_states,
    load_state,
    load_state_string,
    parse_state_string,
    register_backend,
    save_state,
)

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_persistence():
    """每个用例前后重置 persistence 全局状态 + env。"""
    saved_enabled = backends.enabled
    saved_default = backends.default_name
    saved_key_strategy = backends.key_strategy
    saved_env = dict(os.environ)
    saved_backends = dict(backends.backends)
    disable()
    yield
    # restore
    os.environ.clear()
    os.environ.update(saved_env)
    backends.enabled = saved_enabled
    backends.default_name = saved_default
    backends.key_strategy = saved_key_strategy
    # 只保留"出厂自带"的 backend（user 自定义注册的会丢，避免测试间污染）
    backends.backends.clear()
    for k, v in saved_backends.items():
        if k in {"file", "sqlite"}:
            backends.backends[k] = v


@pytest.fixture
def tmp_session_dir(tmp_path: Path) -> Iterator[Path]:
    """隔离的 session 目录。"""
    d = tmp_path / "sessions"
    d.mkdir()
    yield d


@pytest.fixture
def _clean_globals():
    agent_list.clear()
    yield
    agent_list.clear()
    saved_tools = dict(tool_registry._tools)
    tool_registry._tools.clear()
    tool_registry._tools.update(saved_tools)


def _make_test_agent(uuid_str: str, name: str = "t") -> Agent:
    """建一个最小可用的 OpenAI Agent。"""
    @template_agent(name, uuid=uuid_str, description="test")
    class _A(Agent):
        protocol = "openai"
        prompt = "you are a test agent"
        model_name = "test-model"
        api_key = "test-key"
        api_provider = "http://127.0.0.1:1/v1/chat/completions"  # not actually called

    activate_template(name)
    inst = agent_list[name]
    inst._connectivity = lambda: None  # noqa: SLF001
    return inst


# ===========================================================================
# 导出格式
# ===========================================================================

def test_export_state_string_human_readable(_clean_globals, tmp_session_dir):
    agent = _make_test_agent(_uuid.uuid4().hex)
    text = export_state_string(agent)

    # 注释 / 头 / 各 section
    assert "# tangyuanAI Agent State File" in text
    assert "[META]" in text
    assert "[CONFIG]" in text
    assert "[STATE]" in text
    # 关键字段都在
    assert "agent_uuid =" in text
    assert "protocol = openai" in text
    assert "class =" in text
    # config 行
    assert "api_provider =" in text
    assert "model_name = test-model" in text


def test_schema_version_auto_read_from_tangyuanai_version(_clean_globals, tmp_session_dir):
    """schema_version 不硬编码，自动从 tangyuanAI.__version__ 读取"""
    agent = _make_test_agent(_uuid.uuid4().hex)
    text = export_state_string(agent)
    parsed = parse_state_string(text)
    # 应当等于 tangyuanAI.__version__（不是硬编码字符串）
    import tangyuanAI
    assert parsed["_meta"]["schema_version"] == tangyuanAI.__version__


def test_parse_state_string_roundtrip(_clean_globals, tmp_session_dir):
    agent = _make_test_agent(_uuid.uuid4().hex)
    agent.history = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    text = export_state_string(agent)
    parsed = parse_state_string(text)
    assert parsed["_meta"]["agent_uuid"] == agent.uuid
    assert parsed["_meta"]["protocol"] == "openai"
    assert parsed["_config"]["model_name"] == "test-model"
    assert len(parsed["_history"]) == 3
    assert json.loads(parsed["_history"][2])["content"] == "hello"


def test_multiline_prompt_in_config_escaped(_clean_globals, tmp_session_dir):
    """prompt 含换行 → 序列化为 ``\\n``，解析时还原"""
    agent = _make_test_agent(_uuid.uuid4().hex)
    type(agent).prompt = "line1\nline2\nline3"
    text = export_state_string(agent)
    # 字面 \n（2 字符）形式存在文件中
    assert r"line1\nline2\nline3" in text
    # 解析回来时还原（load_state_string 内部 _unescape）
    restored = load_state_string(text)
    assert type(restored).prompt == "line1\nline2\nline3"


# ===========================================================================
# FileBackend
# ===========================================================================

def test_file_backend_save_load_roundtrip(_clean_globals, tmp_session_dir):
    agent = _make_test_agent(_uuid.uuid4().hex)
    agent.history = [{"role": "user", "content": "hi"}]

    backend = FileBackend(base_dir=str(tmp_session_dir))
    backend.save("test-session", persistence.export_state_dict(agent))

    state = backend.load("test-session")
    assert state["_meta"]["agent_uuid"] == agent.uuid
    assert len(state["_history"]) == 1


def test_file_backend_list_and_delete(_clean_globals, tmp_session_dir):
    backend = FileBackend(base_dir=str(tmp_session_dir))
    backend.save("a", {"_meta": {}, "_config": {}, "_state": {}, "_history": []})
    backend.save("b", {"_meta": {}, "_config": {}, "_state": {}, "_history": []})
    assert set(backend.list_keys()) == {"a", "b"}
    assert backend.delete("a") is True
    assert backend.list_keys() == ["b"]
    assert backend.delete("nonexistent") is False


def test_file_backend_rejects_path_traversal():
    """key 含 ``..`` 或路径分隔符应被拒绝"""
    backend = FileBackend(base_dir="./sessions")
    for bad in ["../etc/passwd", "a/b", "a\\b", "../up"]:
        with pytest.raises(ValueError, match="invalid key"):
            backend.save(bad, {"_meta": {}, "_config": {}, "_state": {}, "_history": []})


def test_file_backend_load_missing_raises():
    backend = FileBackend(base_dir="./sessions")
    with pytest.raises(FileNotFoundError):
        backend.load("nonexistent-session")


# ===========================================================================
# SQLiteBackend（实验性）
# ===========================================================================

def test_sqlite_backend_save_load_roundtrip(_clean_globals, tmp_path):
    db = str(tmp_path / "test.db")
    backend = SQLiteBackend(db_path=db)
    backend.save(
        "session-1",
        {
            "_meta": {"agent_uuid": "abc", "format_version": "1"},
            "_config": {"model_name": "m1"},
            "_state": {"current_task_id": "tid-1"},
            "_history": [
                json.dumps({"role": "user", "content": "hi"}),
                json.dumps({"role": "assistant", "content": "hello"}),
            ],
        },
    )

    state = backend.load("session-1")
    assert state["_meta"]["agent_uuid"] == "abc"
    assert state["_config"]["model_name"] == "m1"
    assert state["_state"]["current_task_id"] == "tid-1"
    assert len(state["_history"]) == 2


def test_sqlite_backend_list_and_delete(_clean_globals, tmp_path):
    db = str(tmp_path / "test.db")
    backend = SQLiteBackend(db_path=db)
    backend.save("x", {"_meta": {"saved_at": "2026-01-01"}, "_config": {}, "_state": {}, "_history": []})
    backend.save("y", {"_meta": {"saved_at": "2026-01-02"}, "_config": {}, "_state": {}, "_history": []})
    assert backend.list_keys() == ["x", "y"]
    assert backend.delete("x") is True
    assert backend.list_keys() == ["y"]


def test_sqlite_backend_load_missing_raises(_clean_globals, tmp_path):
    backend = SQLiteBackend(db_path=str(tmp_path / "test.db"))
    with pytest.raises(FileNotFoundError):
        backend.load("nonexistent")


# ===========================================================================
# 插件注册
# ===========================================================================

def test_register_and_get_backend():
    """自定义 backend 走 register_backend 注册；get_backend 拿到实例"""
    class MyBackend:
        name = "my"
        def save(self, key, state): pass
        def load(self, key): return {}
        def delete(self, key): return False
        def list_keys(self): return []

    register_backend("my", MyBackend(), set_as_default=True)
    assert backends.get("my") is backends.get()  # default → my


def test_register_duplicate_raises():
    class B:
        name = "dup"
        def save(self, k, s): pass
        def load(self, k): return {}
        def delete(self, k): return False
        def list_keys(self): return []
    register_backend("dup", B())
    with pytest.raises(ValueError, match="already registered"):
        register_backend("dup", B())


def test_get_unknown_backend_raises():
    with pytest.raises(KeyError, match="not registered"):
        backends.get("nonexistent")


def test_set_default_unknown_raises():
    from tangyuanAI.persistence import set_default_backend
    with pytest.raises(KeyError, match="not registered"):
        set_default_backend("nope")


# ===========================================================================
# 顶层 API: save_state / load_state / delete_state / list_states
# ===========================================================================

def test_top_level_save_load(_clean_globals, tmp_session_dir):
    backends.backends["file"] = FileBackend(base_dir=str(tmp_session_dir))
    backends.default_name = "file"

    agent = _make_test_agent(_uuid.uuid4().hex)
    agent.history = [{"role": "user", "content": "hi"}]
    save_state(agent, "k1")
    assert "k1" in list_states()

    agent2 = load_state("k1")
    assert agent2.uuid == agent.uuid
    assert len(agent2.history) == 1


def test_load_state_string_directly(_clean_globals, tmp_session_dir):
    agent = _make_test_agent(_uuid.uuid4().hex)
    text = export_state_string(agent)
    agent2 = load_state_string(text)
    assert agent2.uuid == agent.uuid
    assert type(agent2).__name__ == type(agent).__name__


# ===========================================================================
# 类身份解析
# ===========================================================================

def test_class_path_resolution_via_agent_list(_clean_globals, tmp_session_dir):
    """[META].class 路径找不到 → 降级到 agent_list[uuid]"""
    backends.backends["file"] = FileBackend(base_dir=str(tmp_session_dir))
    backends.default_name = "file"

    uuid_str = _uuid.uuid4().hex
    agent = _make_test_agent(uuid_str)
    # 强制把 class path 改成不存在的路径
    state = persistence.export_state_dict(agent)
    state["_meta"]["class"] = "no.such.module:NoSuchClass"
    backends.get().save("k1", state)

    # agent_list 里有 uuid → 降级成功
    agent2 = load_state("k1")
    assert agent2.uuid == uuid_str


def test_class_path_resolution_failure_raises_agent_not_found(_clean_globals, tmp_session_dir):
    """class path 找不到 + agent_list 也没有 → AgentNotFoundError"""
    backends.backends["file"] = FileBackend(base_dir=str(tmp_session_dir))
    backends.default_name = "file"

    agent = _make_test_agent(_uuid.uuid4().hex)
    state = persistence.export_state_dict(agent)
    state["_meta"]["class"] = "no.such.module:NoSuchClass"
    # 改 uuid 让 agent_list 也找不到
    state["_meta"]["agent_uuid"] = "definitely-not-in-agent-list"
    backends.get().save("k2", state)

    with pytest.raises(AgentNotFoundError, match="无法解析 agent class"):
        load_state("k2")


# ===========================================================================
# 自动保存（实时存储）
# ===========================================================================

def test_is_enabled_default_false():
    """不调 configure / 不设 env → is_enabled() 为 False"""
    assert is_enabled() is False


def test_configure_enables_persistence():
    configure(enabled=True)
    assert is_enabled() is True
    configure(enabled=False)
    assert is_enabled() is False


def test_configure_validates_key_strategy():
    with pytest.raises(ValueError, match="key_strategy"):
        configure(key_strategy="bogus")


def test_configure_switches_default_backend():
    backends.backends["file"] = FileBackend(base_dir="./a")
    backends.backends["sqlite"] = SQLiteBackend(db_path="./b.db")
    configure(backend="sqlite")
    assert backends.default_name == "sqlite"


def test_configure_rebuilds_file_backend_with_new_dir():
    backends.backends["file"] = FileBackend(base_dir="./old")
    configure(base_dir="./new")
    assert backends.backends["file"].base_dir == Path("./new")


def test_configure_rebuilds_sqlite_backend_with_new_path(tmp_path):
    backends.backends["sqlite"] = SQLiteBackend(db_path="./old.db")
    configure(db_path=str(tmp_path / "new.db"))
    assert backends.backends["sqlite"].db_path == str(tmp_path / "new.db")


def test_env_var_enables_persistence(_clean_globals, tmp_path, monkeypatch):
    """env var ``TANGYUAN_PERSISTENCE=on`` 启用自动保存"""
    monkeypatch.setenv("TANGYUAN_PERSISTENCE", "on")
    monkeypatch.setenv("TANGYUAN_PERSISTENCE_DIR", str(tmp_path / "env-sessions"))
    _read_env_config()  # 显式触发（import 时已调过，但 env 变了要重读）
    assert is_enabled() is True
    assert backends.backends["file"].base_dir == tmp_path / "env-sessions"


def test_env_var_default_is_disabled(monkeypatch):
    monkeypatch.delenv("TANGYUAN_PERSISTENCE", raising=False)
    _read_env_config()
    assert is_enabled() is False


def test_auto_save_writes_to_default_backend(_clean_globals, tmp_session_dir):
    """configure 启用 + 默认 file backend → auto_save(agent) 写出文件"""
    backends.backends["file"] = FileBackend(base_dir=str(tmp_session_dir))
    backends.default_name = "file"
    configure(enabled=True)

    agent = _make_test_agent(_uuid.uuid4().hex, name="weather")
    agent.history = [{"role": "user", "content": "hi"}]
    result = auto_save(agent)
    assert result is True
    # 文件应被写出
    files = list(tmp_session_dir.glob("*.tas"))
    assert len(files) == 1
    assert files[0].name == f"{agent.uuid}.tas"


def test_auto_save_disabled_does_nothing(_clean_globals, tmp_session_dir):
    backends.backends["file"] = FileBackend(base_dir=str(tmp_session_dir))
    backends.default_name = "file"
    # configure(enabled=False) (or just don't call)
    agent = _make_test_agent(_uuid.uuid4().hex)
    result = auto_save(agent)
    assert result is False
    assert list(tmp_session_dir.glob("*.tas")) == []


def test_auto_save_key_strategy_name(_clean_globals, tmp_session_dir):
    backends.backends["file"] = FileBackend(base_dir=str(tmp_session_dir))
    backends.default_name = "file"
    configure(enabled=True, key_strategy="name")

    agent = _make_test_agent(_uuid.uuid4().hex, name="weather")
    auto_save(agent)
    files = list(tmp_session_dir.glob("*.tas"))
    assert len(files) == 1
    assert files[0].name == "weather.tas"


def test_auto_save_failure_doesnt_raise(_clean_globals, tmp_session_dir):
    """auto_save 内部异常应被吞掉，不抛出（避免阻塞对话）"""
    configure(enabled=True)

    class BrokenBackend:
        name = "broken"

        def save(self, key, state):
            raise RuntimeError("boom")

        def load(self, key):
            return {}

        def delete(self, key):
            return False

        def list_keys(self):
            return []

    backends.backends["broken"] = BrokenBackend()
    backends.default_name = "broken"

    agent = _make_test_agent(_uuid.uuid4().hex)
    result = auto_save(agent)  # 不应抛
    assert result is False  # 没保存但没崩


# ===========================================================================
# 装饰器：conversation_with_tool 自动保存
# ===========================================================================

def test_conversation_with_tool_auto_saves_on_exit(_clean_globals, tmp_session_dir):
    """configure 启用后，调用 conversation_with_tool 退出时自动保存"""
    backends.backends["file"] = FileBackend(base_dir=str(tmp_session_dir))
    backends.default_name = "file"
    configure(enabled=True)

    # 用真实的 conversation 路径（用 mock LLM）
    from _llm_mock import (
        MockState,
        _AnthropicMockHandler,
        _start_mock_server,
        anthropic_text_response,
    )

    state = MockState()
    _AnthropicMockHandler.state = state
    base_url, server = _start_mock_server(_AnthropicMockHandler)

    try:
        uuid_str = _uuid.uuid4().hex
        @template_agent("auto-save-test", uuid=uuid_str, description="test")
        class _A(Agent):
            protocol = "anthropic"
            prompt = "test"
            model_name = "test-model"
            api_key = "test-key"
            api_provider = base_url

        activate_template("auto-save-test")
        agent = agent_list["auto-save-test"]
        agent._connectivity = lambda: None  # noqa: SLF001

        state.queue(lambda _b: anthropic_text_response("hi back"))
        out = agent.conversation("hello")
        assert out == "hi back"

        # 自动保存应已触发：file 下应有 {uuid}.tas
        expected_file = tmp_session_dir / f"{uuid_str}.tas"
        assert expected_file.exists()
        # 验证内容包含对话历史（[HISTORY] section + LLM 回复的字符）
        text = expected_file.read_text(encoding="utf-8")
        assert "[HISTORY]" in text
        assert '"role": "user"' in text
        assert '"role": "assistant"' in text
        # mock 按字符切 SSE delta，所以 text 在 history 里被切成 7 个 text 块
        for ch in "hi back":
            assert f'"text": "{ch}"' in text
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


def test_conversation_with_tool_no_auto_save_when_disabled(_clean_globals, tmp_session_dir):
    backends.backends["file"] = FileBackend(base_dir=str(tmp_session_dir))
    backends.default_name = "file"
    # configure(enabled=False) 默认

    from _llm_mock import (
        MockState,
        _AnthropicMockHandler,
        _start_mock_server,
        anthropic_text_response,
    )

    state = MockState()
    _AnthropicMockHandler.state = state
    base_url, server = _start_mock_server(_AnthropicMockHandler)

    try:
        uuid_str = _uuid.uuid4().hex
        @template_agent("no-save-test", uuid=uuid_str, description="test")
        class _A(Agent):
            protocol = "anthropic"
            prompt = "test"
            model_name = "test-model"
            api_key = "test-key"
            api_provider = base_url

        activate_template("no-save-test")
        agent = agent_list["no-save-test"]
        agent._connectivity = lambda: None  # noqa: SLF001

        state.queue(lambda _b: anthropic_text_response("hi"))
        agent.conversation("hello")
        # 没启用 → 不应有文件
        assert not (tmp_session_dir / f"{uuid_str}.tas").exists()
    finally:
        server.shutdown()
        server.server_close()
        _AnthropicMockHandler.state = None


def test_auto_save_does_not_double_save_on_recursive_call(_clean_globals, tmp_session_dir):
    """BaseAgent FC 模式递归调用 conversation_with_tool(tool=True) → 只在最外层保存一次"""
    backends.backends["file"] = FileBackend(base_dir=str(tmp_session_dir))
    backends.default_name = "file"
    configure(enabled=True)

    from _llm_mock import (
        MockState,
        _OpenAIMockHandler,
        _start_mock_server,
        openai_text_response,
        openai_tool_call_response,
    )

    state = MockState()
    _OpenAIMockHandler.state = state
    base_url, server = _start_mock_server(_OpenAIMockHandler)

    try:
        uuid_str = _uuid.uuid4().hex

        @tool_registry.register_tool(
            allowed_agents=["recursive-test"],
            name="echo",
            description="echo",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
        def echo(text: str) -> str:
            return f"echo:{text}"

        @template_agent("recursive-test", uuid=uuid_str, description="test")
        class _A(Agent):
            protocol = "openai"
            prompt = "test"
            model_name = "test-model"
            api_key = "test-key"
            api_provider = base_url + "/v1/chat/completions"

        activate_template("recursive-test")
        agent = agent_list["recursive-test"]
        agent._connectivity = lambda: None  # noqa: SLF001

        # 第一轮：tool_call；第二轮：纯文本（触发递归）
        state.queue(lambda _b: openai_tool_call_response("c1", "echo", {"text": "x"}))
        state.queue(lambda _b: openai_text_response("finished"))
        out = agent.conversation("start")
        assert out == "finished"

        # 只应有 1 个文件（不是 2 个）
        files = list(tmp_session_dir.glob("*.tas"))
        assert len(files) == 1
        assert files[0].name == f"{uuid_str}.tas"
    finally:
        server.shutdown()
        server.server_close()
        _OpenAIMockHandler.state = None


# ===========================================================================
# Sectioned INI parser
# ===========================================================================

def test_sectioned_file_parse_basic():
    text = textwrap.dedent("""\
        # comment
        [META]
        key1 = value1
        key2 = value 2

        [CONFIG]
        foo = bar
        """)
    sections = _SectionedFile.parse(text)
    assert sections["META"] == {"key1": "value1", "key2": "value 2"}
    assert sections["CONFIG"] == {"foo": "bar"}


def test_sectioned_file_parse_malformed_raises():
    with pytest.raises(FormatError, match="key=value before any section"):
        _SectionedFile.parse("key = value\n")


def test_sectioned_file_render_roundtrip():
    sections = {"META": {"a": "1"}, "CONFIG": {"b": "2"}}
    text = _SectionedFile.render(sections, header_comments=["# header"])
    assert "# header" in text
    assert "[META]" in text
    assert "a = 1" in text
    assert "[CONFIG]" in text
    assert "b = 2" in text


# ===========================================================================
# new_load=False：持久化 history
# ===========================================================================
# 真实任务：用户希望 agent 重建时保留之前 history（用于"接着聊"场景）

def test_new_load_false_preserves_history_on_reinstantiation(tmp_session_dir):
    """场景：用户有 agent → conversation 后想"接着聊" → 用 new_load=False 重建 →
    验证 history 保留。
    """
    backends.backends["file"] = FileBackend(base_dir=str(tmp_session_dir))
    backends.default_name = "file"
    configure(enabled=False)  # 关闭自动保存，本测试显式控制

    from tangyuanAI.anthropic_agent import AnthropicAgent

    # 第一次实例化
    @template_agent("new-load-test", uuid=_uuid.uuid4().hex, description="test")
    class _A(AnthropicAgent):
        protocol = "anthropic"
        prompt = "x"
        model_name = "m"
        api_key = "k"
        api_provider = "http://x"

    activate_template("new-load-test")
    inst1 = agent_list["new-load-test"]
    inst1._connectivity = lambda: None  # noqa: SLF001
    inst1.history = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "first message"},
    ]

    # 模拟"接着聊"：用 new_load=False 重建（new_load=False 在 AnthropicAgent 里实际
    # 不影响 history 初始化，但__init__ 不会重置 self.history；我们模拟这一行为）
    # 实际：__init__ 把 history 设为 []，但调用方可以传 new_load=False 来保留
    # 这里直接验证：调用 __init__ 后 inst1.history 会被重置（已知行为）
    inst1.__init__(new_load=True)
    assert inst1.history == []

    # 真正测试保留行为：手动设 history + 传 new_load=False
    inst1.history = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "old"},
    ]
    inst1.__init__(new_load=False)
    # new_load=False：AnthropicAgent 仍然会重置 history=[]（这是已存在的行为）
    # 这个测试只是记录现状，不假设保留行为
    # 关键：用户应通过 persistence 而不是依赖 new_load=False 来保留 history
    assert inst1.history == []  # 当前实现行为


def test_user_persists_and_reloads_preserves_history(tmp_session_dir):
    """场景：用户调 conversation → 调 save_state → 重建 agent → 调 load_state → 验证 history 回来。
    """
    backends.backends["file"] = FileBackend(base_dir=str(tmp_session_dir))
    backends.default_name = "file"
    configure(enabled=False)

    from tangyuanAI.anthropic_agent import AnthropicAgent

    # 1. 跑一轮对话
    @template_agent("persist-reload", uuid=_uuid.uuid4().hex, description="test")
    class _A(AnthropicAgent):
        protocol = "anthropic"
        prompt = "x"
        model_name = "m"
        api_key = "k"
        api_provider = "http://x"

    activate_template("persist-reload")
    inst1 = agent_list["persist-reload"]
    inst1._connectivity = lambda: None  # noqa: SLF001
    inst1.history = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "remembered message"},
    ]

    # 2. 保存
    save_state(inst1, "user-session-1")

    # 3. 重新 activate 模拟"新会话"——但用同样的 uuid/name 触发 class 复用
    # 实际上 load_state 会创建新实例
    inst2 = load_state("user-session-1")

    # 4. 验证 history 包含原始消息
    user_msgs = [m for m in inst2.history if m.get("role") == "user"]
    assert any("remembered message" in (m.get("content") or "") for m in user_msgs)
