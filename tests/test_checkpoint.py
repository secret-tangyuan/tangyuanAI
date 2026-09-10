"""checkpoint.py 单元测试。"""
from __future__ import annotations

from tangyuanAI.checkpoint import (
    FileCheckpointStore,
    Snapshot,
    delete_checkpoint,
    get_default_checkpoint_store,
    list_checkpoints,
)


def test_snapshot_to_dict_roundtrip():
    s = Snapshot(
        snapshot_id="s-1",
        agent_uuid="a-1",
        agent_name="weather",
        history=[{"role": "user", "content": "hi"}],
        pending_tool_calls=[{"task_id": "t1", "tool_name": "get_weather"}],
        extra={"foo": "bar"},
    )
    d = s.to_dict()
    assert d["snapshot_id"] == "s-1"
    assert d["history"][0]["content"] == "hi"
    assert d["extra"]["foo"] == "bar"

    # 反序列化
    s2 = FileCheckpointStore._from_dict(d)
    assert s2.history == s.history
    assert s2.pending_tool_calls == s.pending_tool_calls


def test_file_checkpoint_store_save_load_list_delete(tmp_path):
    base = tmp_path / "snaps"
    store = FileCheckpointStore(str(base))

    # save
    s1 = Snapshot(snapshot_id="abc", agent_uuid="agent-1", agent_name="weather", history=[{"role": "user"}])
    s2 = Snapshot(snapshot_id="def", agent_uuid="agent-1", agent_name="weather", history=[{"role": "user"}])
    s3 = Snapshot(snapshot_id="ghi", agent_uuid="agent-2", agent_name="writer", history=[])
    store.save(s1)
    store.save(s2)
    store.save(s3)

    # load
    got = store.load("abc")
    assert got is not None
    assert got.snapshot_id == "abc"
    assert got.history == [{"role": "user"}]

    assert store.load("nonexistent") is None

    # list (agent_uuid filter)
    list_1 = store.list("agent-1")
    list_2 = store.list("agent-2")
    assert len(list_1) == 2
    assert len(list_2) == 1
    # list all
    list_all = store.list(None)
    assert len(list_all) == 3

    # delete
    assert store.delete("abc") is True
    assert store.load("abc") is None
    assert store.delete("abc") is False  # already gone


def test_file_checkpoint_store_creates_parent_dirs(tmp_path):
    base = tmp_path / "deep" / "snaps"
    store = FileCheckpointStore(str(base))
    s = Snapshot(snapshot_id="x", agent_uuid="u", agent_name="n", history=[])
    store.save(s)
    assert (base / "u" / "x.json").exists()


def test_snapshot_pending_tool_calls_extraction(tmp_path):
    """capture_snapshot 应该把 tool_runner._tasks 里未完成的 task 列出来。"""
    from tangyuanAI.checkpoint import capture_snapshot

    class FakeTask:
        def __init__(self, tid, name, args, done=False):
            self.done = done
            self.tool_name = name
            self.arguments = args
            self.submitted_at = 12345.0

    class FakeRunner:
        _tasks = {
            "t1": FakeTask("t1", "get_weather", {"city": "BJ"}, done=False),
            "t2": FakeTask("t2", "send_email", {"to": "x@y"}, done=True),
            "t3": FakeTask("t3", "calc", {}, done=False),
        }

    class FakeAgent:
        uuid = "u-1"
        name = "test"
        history = [{"role": "user", "content": "hi"}]
        _tool_runner = FakeRunner()

    snap = capture_snapshot(FakeAgent())
    assert snap.agent_uuid == "u-1"
    assert len(snap.history) == 1
    # 只有未 done 的进 pending
    task_ids = {p["task_id"] for p in snap.pending_tool_calls}
    assert task_ids == {"t1", "t3"}


def test_save_checkpoint_round_trip_via_module_functions(tmp_path):
    """save_checkpoint / restore_checkpoint / list_checkpoints 模块级函数。"""
    from tangyuanAI.checkpoint import (
        restore_checkpoint,
        save_checkpoint,
    )

    store = FileCheckpointStore(str(tmp_path / "s"))

    class FakeAgent:
        uuid = "u-A"
        name = "a"
        history = [{"role": "user", "content": "hello"}]
        _tool_runner = None

    snap = save_checkpoint(FakeAgent(), store=store)
    assert snap.snapshot_id

    # restore 到新 agent instance
    agent2 = FakeAgent()
    agent2.history = []
    restore_checkpoint(agent2, snap.snapshot_id, store=store)
    assert agent2.history == [{"role": "user", "content": "hello"}]

    # list
    metas = list_checkpoints(FakeAgent(), store=store)
    assert len(metas) == 1
    assert metas[0]["snapshot_id"] == snap.snapshot_id

    # delete
    assert delete_checkpoint(snap.snapshot_id, store=store) is True
    assert list_checkpoints(FakeAgent(), store=store) == []