"""docs 加载器：扫描 tangyuanAI/docs/*.md，解析 frontmatter + headings。

给 FastAPI 后端提供数据；与 VitePress 侧栏生成逻辑保持一致。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"
SKIP = {"app", "README"}


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """解析 YAML frontmatter，返回 (meta, body)。没有 frontmatter 时返回 ({}, 全文)。"""
    if text.startswith("---\n") or text.startswith("---\r\n"):
        sep = "\n---"
        end = text.find(sep, 4)
        if end > 0:
            fm_block = text[4:end]
            body = text[end + len(sep):].lstrip("\r\n")
            try:
                meta = yaml.safe_load(fm_block) or {}
                if not isinstance(meta, dict):
                    meta = {}
            except Exception:
                meta = {}
            return meta, body
    return {}, text


def _extract_headings(body: str) -> list[dict[str, str]]:
    """抽取 heading → [{level, text}]（正文引用的锚点用 slug 即可）。"""
    out: list[dict[str, str]] = []
    for line in body.splitlines():
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if m:
            out.append({"level": str(len(m.group(1))), "text": m.group(2).strip()})
    return out


def _parse_doc(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)
    stem = path.stem
    slug = str(meta.get("slug") or stem).strip()
    title = str(meta.get("title") or (re.search(r"^#\s+(.+)$", body, re.MULTILINE) or [None, slug]).group(1).strip()).strip()
    try:
        order = int(meta.get("order"))
    except (TypeError, ValueError):
        order = 999
    return {
        "slug": slug,
        "title": title,
        "order": order,
        "icon": str(meta.get("icon") or "DESCRIPTION_OUTLINED").strip(),
        "content": body,
        "headings": _extract_headings(body),
    }


def load_docs() -> dict[str, dict[str, Any]]:
    """扫描 docs/*.md，返回按 order 排序的 {slug: doc}。"""
    idx: dict[str, dict[str, Any]] = {}
    for md in DOCS_DIR.glob("*.md"):
        if md.stem in SKIP:
            continue
        try:
            doc = _parse_doc(md)
        except OSError:
            continue
        idx[doc["slug"]] = doc
    return dict(sorted(idx.items(), key=lambda kv: kv[1]["order"]))


def load_doc(slug: str) -> dict[str, Any] | None:
    return load_docs().get(slug)


def search_docs(q: str) -> list[dict[str, str]]:
    """标题 + 正文子串搜索，返回 [{slug, title}]。"""
    q = q.strip().lower()
    if not q:
        return []
    hits: list[dict[str, str]] = []
    for doc in load_docs().values():
        if q in doc["title"].lower() or q in doc["content"].lower():
            hits.append({"slug": doc["slug"], "title": doc["title"]})
    return hits
