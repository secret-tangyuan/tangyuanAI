"""
示例 1：单 Agent 基础用法

这个示例演示如何创建一个简单的 Agent 并与之对话。
"""
import os

import tangyuanAI
from dotenv import load_dotenv
from tangyuanAI.Agent_list import activate_template

load_dotenv()


@tangyuanAI.template_agent(
    "simple_agent",
    uuid="001",
    description="简单问答 Agent 模板",
)
class SimpleAgent(tangyuanAI.Agent):
    """一个简单的问答助手 Agent"""
    protocol = "openai"  # 一行声明走 OpenAI Chat Completions 协议
    prompt = "你是一个名为汤圆 AI 的简单问答助手，友好地回答用户的问题"
    api_provider = "https://api.example.com/v1/chat/completions"
    model_name = os.getenv("OPENAI_MODEL")
    api_key = os.getenv("API_KEY")


if __name__ == "__main__":
    activate_template("simple_agent")

    # 获取 Agent 实例
    agent = tangyuanAI.agent_list["simple_agent"]

    # 开始对话
    print("=== 简单 Agent 示例 ===")
    agent.conversation("你好，请介绍一下你自己")
