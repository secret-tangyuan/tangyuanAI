"""tangyuanAI checkpoint —— v1.4.0 引入的 agent 状态快照 / 恢复。

设计目标:
- agent 跑长任务中途崩溃可恢复
- 每 FC 轮 round 自动 mid-flight snapshot
- 用户可手动 `agent.checkpoint()` / `agent.resume(snapshot_id)`
- 检查点存到 `.tangyuan_checkpoints/<agent_uuid>/<snapshot_id>.json`(默认)
- 与现有 `.tas` 持久化解耦:`.tas` 是"对话完成态",checkpoint 是"对话中途态"
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_logger = logging.getLogger(__name__)


@dataclass
class Snapshot:
    """agent 状态快照。

    snapshot_id 全局唯一。
    history 快照的是当时 _AgentCommon.history 的 JSONL 化(OpenAI messages list)。
    pending_tool_calls: 当时还有哪些 tool_use_id 在 tool_runner 里 inflight
    extra: 自由扩展字段(agent state / config snapshot 等)
    """
    snapshot_id: str
    agent_uuid: str
    agent_name: str
    created_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    history: list = field(default_factory=list)
    pending_tool_calls: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "agent_uuid": self.agent_uuid,
            "agent_name": self.agent_name,
            "created_at_ms": self.created_at_ms,
            "history": self.history,
            "pending_tool_calls": self.pending_tool_calls,
            "extra": self.extra,
        }


class CheckpointStore(ABC):
    """快照存储抽象。"""

    @abstractmethod
    def save(self, snapshot: Snapshot) -> None: ...

    @abstractmethod
    def load(self, snapshot_id: str) -> Optional[Snapshot]: ...

    @abstractmethod
    def list(self, agent_uuid: Optional[str] = None) -> list: ...

    @abstractmethod
    def delete(self, snapshot_id: str) -> bool: ...


class FileCheckpointStore(CheckpointStore):
    """写到 `{base_dir}/{agent_uuid}/{snapshot_id}.json`。"""

    def __init__(self, base_dir: str = ".tangyuan_checkpoints"):
        self.base_dir = Path(base_dir)

    def _path(self, agent_uuid: str, snapshot_id: str) -> Path:
        return self.base_dir / agent_uuid / f"{snapshot_id}.json"

    def save(self, snapshot: Snapshot) -> None:
        p = self._path(snapshot.agent_uuid, snapshot.snapshot_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(snapshot.to_dict(), ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def load(self, snapshot_id: str) -> Optional[Snapshot]:
        # 不知道 agent_uuid,扫所有子目录
        if not self.base_dir.exists():
            return None
        for path in self.base_dir.rglob(f"{snapshot_id}.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return self._from_dict(data)
            except Exception:
                _logger.warning(f"snapshot {snapshot_id} 加载失败: {path}")
                return None
        return None

    def list(self, agent_uuid: Optional[str] = None) -> list:
        if not self.base_dir.exists():
            return []
        out = []
        pattern_dir = self.base_dir / agent_uuid if agent_uuid else self.base_dir
        if not pattern_dir.exists():
            return []
        for path in pattern_dir.rglob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                meta = {
                    "snapshot_id": data.get("snapshot_id"),
                    "agent_uuid": data.get("agent_uuid"),
                    "agent_name": data.get("agent_name"),
                    "created_at_ms": data.get("created_at_ms"),
                    "path": str(path),
                }
                out.append(meta)
            except Exception:
                continue
        out.sort(key=lambda m: m.get("created_at_ms") or 0, reverse=True)
        return out

    def delete(self, snapshot_id: str) -> bool:
        if not self.base_dir.exists():
            return False
        for path in self.base_dir.rglob(f"{snapshot_id}.json"):
            try:
                path.unlink()
                return True
            except Exception:
                return False
        return False

    @staticmethod
    def _from_dict(data: dict) -> Snapshot:
        return Snapshot(
            snapshot_id=data["snapshot_id"],
            agent_uuid=data.get("agent_uuid", ""),
            agent_name=data.get("agent_name", ""),
            created_at_ms=data.get("created_at_ms", time.time() * 1000),
            history=data.get("history", []),
            pending_tool_calls=data.get("pending_tool_calls", []),
            extra=data.get("extra", {}),
        )


# 全局默认 store
_default_store: CheckpointStore = FileCheckpointStore()


def get_default_checkpoint_store() -> CheckpointStore:
    return _default_store


def set_default_checkpoint_store(store: CheckpointStore) -> None:
    """覆盖默认 store。生产可换 RedisCheckpointStore 等。"""
    global _default_store
    _default_store = store


# ============================================================
# checkpoint() / restore() 函数
# ============================================================


def capture_snapshot(agent: Any) -> Snapshot:
    """捕获 agent 当前状态为 Snapshot(不存)。"""
    pending = []
    runner = getattr(agent, "_tool_runner", None)
    if runner is not None:
        try:
            # tool_runner._tasks: dict[id, _Task]
            for tid, task in getattr(runner, "_tasks", {}).items():
                if not getattr(task, "done", False):
                    pending.append({
                        "task_id": tid,
                        "tool_name": getattr(task, "tool_name", None),
                        "arguments": getattr(task, "arguments", None),
                        "submitted_at": getattr(task, "submitted_at", None),
                    })
        except Exception:
            pass
    return Snapshot(
        snapshot_id=uuid.uuid4().hex,
        agent_uuid=getattr(agent, "uuid", "") or "",
        agent_name=getattr(agent, "name", "") or "",
        history=list(getattr(agent, "history", []) or []),
        pending_tool_calls=pending,
    )


def save_checkpoint(
    agent: Any,
    *,
    store: Optional[CheckpointStore] = None,
) -> Snapshot:
    """立即捕获并存盘。返回 Snapshot(含 snapshot_id)。"""
    snap = capture_snapshot(agent)
    (store or get_default_checkpoint_store()).save(snap)
    return snap


def restore_checkpoint(
    agent: Any,
    snapshot_id: str,
    *,
    store: Optional[CheckpointStore] = None,
) -> Snapshot:
    """从 snapshot_id 恢复 agent 状态。返回 Snapshot。"""
    s = store or get_default_checkpoint_store()
    snap = s.load(snapshot_id)
    if snap is None:
        raise KeyError(f"snapshot {snapshot_id} 未找到")
    agent.history = list(snap.history)
    return snap


def list_checkpoints(
    agent: Any = None,
    *,
    store: Optional[CheckpointStore] = None,
) -> list:
    """列 agent 的所有 snapshot metadata。agent 为 None 则列所有 agent 的。"""
    s = store or get_default_checkpoint_store()
    uid = getattr(agent, "uuid", None) if agent else None
    return s.list(uid)


def delete_checkpoint(
    snapshot_id: str,
    *,
    store: Optional[CheckpointStore] = None,
) -> bool:
    s = store or get_default_checkpoint_store()
    return s.delete(snapshot_id)


__all__ = [
    "Snapshot",
    "CheckpointStore",
    "FileCheckpointStore",
    "get_default_checkpoint_store",
    "set_default_checkpoint_store",
    "capture_snapshot",
    "save_checkpoint",
    "restore_checkpoint",
    "list_checkpoints",
    "delete_checkpoint",
]