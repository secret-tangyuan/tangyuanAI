# 08 Knowledge Base (RAG)

> 🎯 学完能给 agent 接知识库,做文档检索增强问答。

## 概念

tangyuanAI 内置 `Knowledge` 类,封装了 RAG 三大能力:
- **文档加载**(PDF / DOCX / HTML / Markdown / ...)
- **文本切分**(langchain-text-splitters / tiktoken-aware)
- **检索**(全文 + 向量 + 可选重排)

默认 vendored 实现(`kb/`)无需额外依赖。要换实现就注册第三方 plugin。

## 5 行代码起步

```python
import tangyuanAI
from tangyuanAI.kb import Knowledge

kb = Knowledge(name="docs")
kb.add("./docs")                              # 加载整个目录

agent = tangyuanAI.agent_list["qa"]
agent.conversation("根据文档回答:tangyuanAI 的核心定位是什么?")
# framework 自动 kb.query() 把相关片段塞进 agent 上下文
```

## 多实例隔离

```python
kb_main = Knowledge(name="main")
kb_legal = Knowledge(name="legal")
# 不同 agent 用不同 kb,互不串
```

## 完整 demo

- [`examples/example4_kb_basic.py`](examples/example4_kb_basic.py) —— KB 加载 / 检索 / 问答集成

## 进阶

- [`docs/kb.md`](../kb.md) —— `Knowledge` 完整 API / 重排 / chunking 策略

## 常见问题

**Q: 默认用哪个向量库?**
A: `qdrant-client`(已依赖),本地嵌入式模式(`qdrant-client` 自带)或 server 模式(`QDRANT_URL` 环境变量)。

**Q: 我想换 embedding 模型?**
A: `Knowledge(embedding="text-embedding-3-large")` 或自定义通过 `register_feature` 替换默认实现。