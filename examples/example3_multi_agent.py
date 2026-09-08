"""
示例 3：多 Agent 协作

这个示例演示如何创建多个 Agent 并让它们相互协作。
"""
import os

import tangyuanAI
from dotenv import load_dotenv
from tangyuanAI.Agent_list import activate_template

load_dotenv()


# ==================== 时间查询 Agent ====================

@tangyuanAI.template_agent(
    "time_agent",
    uuid="time-uuid",
    description="时间 Agent：响应时间查询（演示用，返回固定日期）",
)
class TimeAgent(tangyuanAI.Agent):
    """时间管理者，负责提供当前时间"""
    protocol = "openai"
    prompt = "你是时间管理者，当被询问时间时，直接回答当前时间是 2026 年 3 月 15 日"
    api_provider = "https://api.example.com/v1/chat/completions"
    model_name = os.getenv("OPENAI_MODEL")
    api_key = os.getenv("API_KEY")


# ==================== 调度 Agent ====================

@tangyuanAI.template_agent(
    "scheduling_agent",
    uuid="schedule-uuid",
    description="调度 Agent：通过 ask_for_help 委托子 Agent 完成子任务",
)
class SchedulingAgent(tangyuanAI.Agent):
    """调度助手，可以请求其他 Agent 帮助"""
    protocol = "openai"
    prompt = "你是一个调度助手，当需要查询时间时，使用 ask_for_help 工具请求 time_agent 帮助"
    api_provider = "https://api.example.com/v1/chat/completions"
    model_name = os.getenv("OPENAI_MODEL")
    api_key = os.getenv("API_KEY")


# ==================== 运行示例 ====================

if __name__ == "__main__":
    activate_template("time_agent")
    activate_template("scheduling_agent")

    print("=== 多 Agent 协作示例 ===")

    # 获取调度 Agent
    scheduler = tangyuanAI.agent_list["scheduling_agent"]

    # 请求调度 Agent 查询时间（它会向 time_agent 求助）
    scheduler.conversation(
        "你好，请请求 time_agent 帮你查看当前时间"
    )

    # 查看已注册的 Agent
    print("\n=== 已注册的 Agent ===")
    print(tangyuanAI.tool_registry.list_tools())
