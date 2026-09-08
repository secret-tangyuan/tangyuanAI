# 图像理解输入（vision）

tangyuanAI 支持把图片传给 LLM（OpenAI Chat Completions / Anthropic Messages / OpenAI Responses API 三协议）。

适用模型：DeepSeek `deepseek-v4-flash-vision-exp`、GPT-4o / GPT-4-vision、Anthropic Claude 3+ 等所有支持 vision 的多模态模型。

---

## 1. 传图方式

支持 3 种形态，与 DeepSeek / OpenAI / Anthropic 文档一致：

### 1.1 Base64 编码图片（内联）

字符串可以是裸 base64 或 `data:` URI。`media_type` 缺省时从 magic bytes 自动推断 JPEG / PNG / GIF / WebP。

```python
# 裸 base64（自动推断 media_type）
agent.conversation(
    "这张图片里有什么？",
    images=[base64.b64encode(jpeg_bytes).decode("ascii")],
)

# 显式 media_type（覆盖推断）
agent.conversation(
    "这张图片里有什么？",
    images=[{"data": b64, "media_type": "image/jpeg"}],
)
```

### 1.2 外部图片 URL

字符串以 `http://` / `https://` 起头时自动识别为 URL。URL ≤ 8192 字符，图片 ≤ 32 MiB，60 秒内下载完成。

```python
agent.conversation(
    "描述这张图片",
    images=["https://example.com/image.jpg"],
)

# 带 detail 字段（仅 URL/base64 有效）
agent.conversation(
    "粗略描述",
    images=[{"url": "https://example.com/image.jpg", "detail": "low"}],
)
```

### 1.3 DeepSeek Files API（`file_id`）

通过 Files API 上传一次图片，后续用 `file_id` 引用。受 64 MiB 单图上限保护，不受 32 MiB 内联限制。

```python
agent.conversation(
    "这张图片里有什么？",
    images=[{"file_id": "file-api-xxxxxxxxxxxxxxxx"}],
)
```

> **Anthropic Files API 提示**：用 Anthropic 协议 + `file_id` 时，框架会自动注入请求头
> `anthropic-beta: files-api-2025-04-14`（通过 `_messages_use_files_api` 检测）。
> 用户无需手动加 header。

---

## 2. 三协议差异

| 协议 | 协议标识 | Chat Completions 块结构 | Anthropic 块结构 | Responses 块结构 |
|---|---|---|---|---|
| OpenAI Chat | `protocol="openai"` | `{"type": "image_url", "image_url": {"url", "detail"}}` / `{"type": "file", "file_id"}` | — | — |
| Anthropic | `protocol="anthropic"` | — | `{"type": "image", "source": {"type": "url\|base64\|file", ...}}` | — |
| OpenAI Responses | `protocol="openai-responses"` | — | — | `{"type": "input_image", "image_url", "detail"}` / `{"type": "input_file", "file_id"}` |

`image_input.to_openai_block` / `to_anthropic_block` / `to_responses_block` 三个 helper 负责归一化。

---

## 3. `detail` 字段

只对 URL / base64 图片有效（`file_id` 不支持），取值 `low` / `high` / `original` / `auto`：
- `low`：推理前缩放到 512×512，更快更省 token
- `high` / `original`：保留原图（两者等价）
- `auto`：自动选择（当前等价于 `original`）

```python
# OpenAI Chat
images=[{"url": "https://...", "detail": "low"}]
# OpenAI Responses
images=[{"url": "https://...", "detail": "low"}]
# file_id 自动忽略 detail
images=[{"file_id": "file-api-...", "detail": "low"}]  # detail 被忽略
```

---

## 4. 限制（DeepSeek vision 模型）

| 项 | 数值 |
|---|---|
| 支持格式 | JPEG / PNG / GIF / WebP |
| 单图最大（base64 / URL） | 32 MiB |
| 单图最大（Files API file_id） | 64 MiB |
| 请求体总大小 | 48 MiB（不含 file_id 图片最多 64 MiB；含 file_id 最高 200 MiB） |
| 外链 URL 长度 | 8192 字符 |
| 单请求图片数 | 600 |
| 单图最大像素（单边） | 8192 px；≥15 张时降为 4096 px |
| 图片出现位置 | **仅 user 消息**（system / assistant 携带会返回 400） |

---

## 5. 示例

```python
import base64
from tangyuanAI import Agent

agent = Agent(
    api_key="...",
    api_provider="https://api.deepseek.com",
    protocol="openai",  # 或 "anthropic" / "openai-responses"
    model_name="deepseek-v4-flash-vision-exp",
    prompt="你是图像理解助手。",
)

# URL
agent.conversation("图里有几只猫？", images=["https://.../cats.jpg"])

# 内联 base64
with open("local.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode("ascii")
agent.conversation("描述这张图", images=[b64])

# Files API
agent.conversation(
    "这张图里有什么？",
    images=[{"file_id": "file-api-xxxxxxxxxxxxxxxx"}],
)
```