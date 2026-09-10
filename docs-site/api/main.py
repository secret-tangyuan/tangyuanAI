"""tangyuanAI 文档站 FastAPI 后端（开发期动态拉取 docs/*.md）。

设计上与 VitePress 侧栏共用同一份 frontmatter 解析逻辑（见 docs_loader.py）。
生产环境建议直接用 VitePress 静态构建，本后端主要用于 dev 期的热加载演示。
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .docs_loader import load_doc, load_docs, search_docs

app = FastAPI(
    title="tangyuanAI Docs API",
    version="0.1.0",
    description="tangyuanAI/docs/*.md 的动态加载后端，frontmatter 驱动。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "source": "tangyuanAI/docs/"}


@app.get("/api/docs/list")
def list_docs() -> list[dict]:
    """返回文档列表（按 frontmatter order 排序），不含 content。"""
    return [
        {"slug": d["slug"], "title": d["title"], "order": d["order"], "icon": d["icon"]}
        for d in load_docs().values()
    ]


@app.get("/api/docs/{slug}")
def get_doc(slug: str) -> dict:
    """返回单篇文档（含 markdown content 和 headings）。"""
    doc = load_doc(slug)
    if not doc:
        raise HTTPException(404, f"doc not found: {slug}")
    return doc


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)) -> list[dict]:
    """标题 + 正文子串搜索。"""
    return search_docs(q)
