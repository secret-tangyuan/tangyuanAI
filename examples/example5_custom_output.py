"""
示例 5：自定义输出处理

这个示例演示如何重写 Agent 的输出方法实现自定义处理。
"""
import os

import tangyuanAI
from dotenv import load_dotenv
from tangyuanAI.Agent_list import activate_template

load_dotenv()


@tangyuanAI.template_agent(
    "custom_agent",
    uuid="custom-uuid",
    description="自定义输出格式 Agent 模板",
)
class CustomAgent(tangyuanAI.Agent):
    """具有自定义输出处理的 Agent"""
    protocol = "openai"
    prompt = "你是一个具有自定义输出格式的助手"
    api_provider = "https://api.example.com/v1/chat/completions"
    model_name = os.getenv("OPENAI_MODEL")
    api_key = os.getenv("API_KEY")

    def out(self, content):
        """重写输出方法，实现自定义处理"""
        if content.get("tool_name"):
            print(f"[TOOL] 调用：{content.get('tool_name')}")
            print(f"       参数：{content.get('tool_parameter')}")
            return
        if content.get("task"):
            print("\n[DONE] 任务完成")
        elif content.get("other"):
            print(f"[INFO] {content.get('message')}")
        else:
            print(content.get("message"), end="")


if __name__ == "__main__":
    activate_template("custom_agent")
    agent = tangyuanAI.agent_list["custom_agent"]

    print("=== 自定义输出示例 ===")
    agent.conversation("你好，请用你的方式回答")
