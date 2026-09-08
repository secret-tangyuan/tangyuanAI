"""
示例：Agent（protocol = "anthropic"）使用自定义服务商

`Agent` 工厂基类 + `protocol` 字段切换协议是推荐写法；
不再需要 import `AnthropicAgent`（v1.2.0 后该别名会从 `tangyuanAI.anthropic_agent` 移除）。

AnthropicAgent 不只面向官方 api.anthropic.com —— 你可以指向任意兼容
Anthropic Messages API 的服务。
**注意**：v0.2.2+ 不再保留 api_provider 默认值，必须显式写出 endpoint。

  1) 官方 Anthropic:        https://api.anthropic.com
  2) 第三方代理 / 加速网关:  https://your-proxy.example.com
  3) AWS Bedrock:           bedrock-runtime.<region>.amazonaws.com
                           (需要通过 InvokeModel 接口，通常需要自定义 header)
  4) 自家 LLM 网关（OpenRouter / one-api / newapi 等):
                           https://your-gateway.example.com/anthropic
  5) 本地代理（litellm / claude-code-router）:
                           http://127.0.0.1:4000

框架的 _endpoint() 会智能处理：
  - 末尾是 /v1/messages → 原样使用
  - 末尾是 /v1         → 拼上 /messages
  - 其他               → 拼上 /v1/messages
所以你可以填各种层级的 base URL。

如果你的网关有特殊需求（比如 Bedrock 需要 aws-* 头），可以直接覆盖
``__init__`` 里的 self.headers 字典。
"""
import os

import tangyuanAI
from dotenv import load_dotenv
from tangyuanAI.Agent_list import activate_template

load_dotenv()


# ---------- 场景 1：官方 Anthropic API ----------
@tangyuanAI.template_agent(
    "official_agent",
    uuid="official-anthropic-uuid",
    description="官方 Anthropic API Agent 模板",
)
class OfficialAgent(tangyuanAI.Agent):
    """走官方 api.anthropic.com —— 必须显式写 api_provider（v0.2.2+ 不留默认）"""
    protocol = "anthropic"                                       # 一行切协议
    prompt = "你是一个简洁的助手。"
    api_provider = "https://api.anthropic.com"                 # 必须显式给出
    model_name = os.getenv("ANTHROPIC_MODEL")
    api_key = os.getenv("ANTHROPIC_API_KEY")


# ---------- 场景 2：自家代理 / 加速网关 ----------
@tangyuanAI.template_agent(
    "proxy_agent",
    uuid="proxy-anthropic-uuid",
    description="第三方 Anthropic 兼容代理 Agent 模板",
)
class ProxyAgent(tangyuanAI.Agent):
    """走你自己的 Anthropic 兼容代理"""
    protocol = "anthropic"
    prompt = "你是一个简洁的助手。"
    api_provider = "https://your-proxy.example.com"          # 框架会自动拼成 /v1/messages
    model_name = os.getenv("ANTHROPIC_MODEL")
    api_key = os.getenv("ANTHROPIC_API_KEY")                  # 网关可能用自己的 key，这里只是演示


# ---------- 场景 3：直接填完整 endpoint URL ----------
@tangyuanAI.template_agent(
    "full_url_agent",
    uuid="full-url-uuid",
    description="完整 endpoint URL Agent 模板（不重复拼 /v1/messages）",
)
class FullUrlAgent(tangyuanAI.Agent):
    """如果你已经拿到完整的 messages URL，直接填进去即可（不会重复拼）"""
    protocol = "anthropic"
    prompt = "你是一个简洁的助手。"
    api_provider = "https://your-proxy.example.com/v1/messages"
    model_name = os.getenv("ANTHROPIC_MODEL")
    api_key = os.getenv("ANTHROPIC_API_KEY")


# ---------- 场景 4：网关要求额外 header ----------
@tangyuanAI.template_agent(
    "custom_header_agent",
    uuid="custom-header-uuid",
    description="自定义 HTTP header Agent 模板（网关要求 X-Tenant-Id 等）",
)
class CustomHeaderAgent(tangyuanAI.Agent):
    """如果网关需要额外 header（如 Authorization bearer / X-Tenant-Id），
    在 __init__ 里覆盖 self.headers 即可。"""

    protocol = "anthropic"
    prompt = "你是一个简洁的助手。"
    api_provider = "https://your-gateway.example.com/anthropic"
    model_name = os.getenv("ANTHROPIC_MODEL")
    api_key = "internal-tenant-key"

    def __init__(self, new_load=True):
        super().__init__(new_load=new_load)
        # 覆盖 header：例如加上租户标识
        self.headers["X-Tenant-Id"] = "tenant-001"
        # 也可以替换 api_key 的 header 名（Bridgerton 兼容模式）
        # self.headers["Authorization"] = f"Bearer {self.api_key}"
        # self.headers.pop("x-api-key", None)


if __name__ == "__main__":
    activate_template("proxy_agent")
    agent = tangyuanAI.agent_list["proxy_agent"]
    print(f"Agent 走 endpoint：{agent._endpoint()}")
    # agent.conversation("你好")
