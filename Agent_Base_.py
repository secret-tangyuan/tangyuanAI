# -*- coding: utf-8 -*-
"""⚠️ v0.4.2+ DEPRECATED — **计划在 v1.2.0 移除**：本模块旧实现仍保留兼容，但 bug 修复 / 瘦身只发生在 ``tangyuanAI.agent``。

OpenAI 协议 Agent 基类的兼容路径（``tangyuanAI.Agent_Base_.Agent``）。
逻辑、bug 修复、瘦身现在只在 ``tangyuanAI.agent._OpenAIBase``
（对外别名 :class:`tangyuanAI.BaseAgent`）里维护。

**v1.2.0 移除计划**：本模块（``tangyuanAI.Agent_Base_``）和 ``tangyuanAI.anthropic_agent`` 都将在
1.2.0 删除。请尽快迁到 ``from tangyuanAI import BaseAgent, AnthropicAgent``。

新代码请直接用::

    from tangyuanAI import BaseAgent               # 推荐
    class MyAgent(BaseAgent): ...

import 本模块时打印一次 ``DeprecationWarning``；旧 :class:`Agent` 类保留以保持
``from tangyuanAI.Agent_Base_ import Agent`` 的旧 import 路径继续可用。
"""
from __future__ import annotations

import warnings as _warnings

# 模块加载即打 deprecation warning —— 任何 `from tangyuanAI.Agent_Base_ import ...`
# 都会经过 module 求值，触发一次告警。
_warnings.warn(
    "tangyuanAI.Agent_Base_ 已弃用；**计划在 v1.2.0 删除**。新代码请用 tangyuanAI.BaseAgent "
    "（实现在 tangyuanAI.agent._OpenAIBase）。",
    DeprecationWarning,
    stacklevel=2,
)

import json  # noqa: E402  (排在 _warnings.warn 之后是故意的：让 deprecation 先发出)
import os  # noqa: E402
import platform  # noqa: E402
import re  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from typing import Any, Optional  # noqa: E402

from bs4 import BeautifulSoup  # noqa: E402

try:
    from .agent_tool import _builtin_promote_overrides, builtin_tool, tool_registry
    from .llm_transport import (
        ChatRequest,
        HttpxOpenAITransport,
        LLMResponse,
    )
    from .logging_config import logger  # 配置日志
    from .persistence import _auto_save, _auto_save_async  # v0.3.2+ 自动持久化装饰器
except Exception:
    raise ImportError("不可单独执行")


class Agent():
    """
    所有具体 Tangyuan 必须实现四个属性：
        api_key
        api_provider
        model_name
        prompt
    """
    prompt = None
    api_provider = None
    model_name = None
    api_key = None
    fc_model = True # 现在xml工具调用改为下位支持，如有bug修复优先级降低
    stream = True
    description = None
    tool_timeout: float = 60.0  # 工具调用单次超时；超时后转入后台 future
    tool_max_workers: int = 8  # 工具执行线程池大小

    # ---------------- 类层级钩子：子类覆盖 @builtin_tool 方法时自动复用父类的 meta ----------------
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _builtin_promote_overrides(cls)
        # 一次性检测：子类覆写 pack() 但没有覆写 out() 时打 warning。
        # 用 cls.__dict__ 检测"本类自己定义"，避免在多级继承下误判祖先类
        # （如 AnthropicAgent 继承 Agent.BaseAgent 的 __init_subclass__ 时，
        #  `Agent` 名字在不同上下文里指向不同类，``cls.out is Agent.out`` 不可靠）。
        has_own_pack = "pack" in cls.__dict__
        has_own_out = "out" in cls.__dict__
        if has_own_pack and not has_own_out:
            logger.warning(
                "[tangyuanAI] 检测到子类 {} 覆写了 pack() 但没有覆写 out()。"
                "如果你想自定义输出行为（流式 / UI / 自定义 logger 等），"
                "请覆写 out(content) 而不是 pack() ——"
                "pack() 只负责把事件打包成 dict 然后调用 self.out(content) 丢出去。",
                cls.__name__,
            )
    # ---------------- 通用构造 ----------------
    def __init__(self,new_load=True):
        self.uuid=self.__class__.uuid
        self.name=self.__class__.name
        self.stream_run=False
        self.current_task_id = None  # 当前任务 ID
        self.tool_call_hooks = []     # 工具调用钩子列表
        # 工具执行线程池：超时即转后台 future，允许长线任务不阻塞对话循环
        from .tool_runner import ToolRunner
        self._tool_runner = ToolRunner(
            timeout=self.tool_timeout,
            max_workers=self.tool_max_workers,
        )
        agent_name = getattr(self.__class__, 'name', None) or getattr(self.__class__, '__name__', None)
        if agent_name and self.uuid:
            tool_registry.register_agent_uuid(self.uuid, agent_name)

        # 获取该 agent 有权限的所有工具信息
        tools_info = tool_registry.get_all_tools_info(self.uuid)
        tools_prompt = ""
        tools_list = list(tools_info.keys())

        # 通过自动收集器获取 @builtin_tool 装饰的内置工具 schema
        builtin_schemas = tool_registry.collect_builtin_tools(self)
        builtin_names = {s["function"]["name"] for s in builtin_schemas}
        for name in builtin_names:
            if name not in tools_list:
                tools_list.append(name)

        # 生成工具提示
        if tools_list:
            tools_prompt = "\n\n你可以使用以下工具：\n"
            # 注册的工具
            for tool_name, tool_info in tools_info.items():
                tools_prompt += f"- {tool_name}: {tool_info['description']}\n"
            # 内置工具（自动来自 @builtin_tool 装饰器）
            for s in builtin_schemas:
                n = s["function"]["name"]
                if n in tools_list and n not in tools_info:
                    tools_prompt += f"- {n}: {s['function']['description']}\n"
            if not self.fc_model:
                tools_prompt += "在使用xml格式的工具时应采用（无参数调用）<工具名></工具名>（含参数调用）<工具名><参数1>放入你想传入的内容</参数1>...</工具名>"

        # 注入 Skills 信息
        try:
            from .skill import skill_registry
            tools_prompt += skill_registry.get_skills_prompt_text(self.uuid)
        except ImportError:
            pass


        prompt = self.prompt + tools_prompt + ", 你的uuid " + str(self.uuid)
        logger.debug(f"Agent {self.name} 初始化，系统提示词长度：{len(prompt)}")
        # print(prompt)
        if new_load:
            self.history = [{"role": "system", "content": prompt}]
        else:
            self.history[0] = {"role": "system", "content": prompt}
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.os_name = platform.system()
        self.conversations_folder = os.getcwd()
        if self.os_name == "Windows":
            self.os_main_folder = os.getenv("USERPROFILE")
        elif self.os_name == "Linux":
            self.os_main_folder = os.path.expanduser("~")
        elif self.os_name == "Darwin":
            self.os_main_folder = os.getenv("HOME")

        threading.Thread(target=self.Connectivity, daemon=True).start()

    # ---------------- 辅助方法 ----------------
    def _generate_task_id(self) -> str:
        """生成唯一任务 ID"""
        return str(uuid.uuid4())

    def _get_timestamp(self) -> int:
        """获取当前时间戳（毫秒级）"""
        return int(time.time() * 1000)

    def register_tool_hook(self, hook_func):
        """
        注册工具调用钩子
        hook_func 签名：hook_func(event_type, tool_name, tool_args, tool_result, task_id)
        event_type: 'before' | 'after' | 'error'
        """
        self.tool_call_hooks.append(hook_func)

    # ---------------- 持久化（v0.3.2+）----------------
    def save_state(self, key: str, backend: Optional[str] = None) -> None:
        """把当前 agent 状态保存到指定后端。

        Wrapper around :func:`tangyuanAI.save_state`. 详见
        ``tangyuanAI/persistence.py`` 顶部的格式说明。
        """
        from .persistence import save_state as _save_state
        _save_state(self, key, backend=backend)

    @classmethod
    def load_state(cls, key: str, backend: Optional[str] = None) -> "Agent":
        """从指定后端加载 key 对应的 agent 状态，返回新实例。

        类路径解析失败时（如原类已被删除）会回退到 ``agent_list[uuid]``；
        都找不到时抛 :class:`AgentNotFoundError`。
        """
        from .persistence import load_state as _load_state
        return _load_state(key, backend=backend)

    def _execute_hooks(self, event_type, tool_name, tool_args, tool_result=None):
        """执行所有注册的钩子"""
        for hook in self.tool_call_hooks:
            try:
                hook(
                    event_type=event_type,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    tool_result=tool_result,
                    task_id=self.current_task_id
                )
            except Exception as e:
                logger.error(f"钩子执行失败：{e}")

    # ---------------- 连通性测试 ----------------
    def Connectivity(self):
        """异步 ping：走 HTTPClient，不重试（max_retries=0）。"""
        from .errors import APIError
        from .http_utils import HTTPClient

        try:
            client = HTTPClient()
            payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": "你好"}],
                "stream": self.stream,
                "stream_options": {"include_usage": True},
                "max_tokens": 1,
            }
            rsp = client.post(
                self.api_provider,
                headers=self.headers,
                json=payload,
                max_retries=0,
            )
            ok = 200 <= rsp.status_code < 300
        except APIError as e:
            logger.error(f"{self.name} 连接测试未通过：{e}")
            return False
        except Exception as e:
            logger.error(f"{self.name} 连接异常：{e}")
            return False

        if ok:
            logger.info(f"{self.name} 连接正常")
        else:
            logger.error(f"{self.name} 连接测试未通过：status={rsp.status_code}")
        return ok

    # ---------------- 主对话函数 ----------------
    @_auto_save
    def conversation(
        self,
        messages=None,
        *,
        tooluse: bool = True,
        addhistory: bool = True,
        images=None,
    ):
        """
        进行对话，支持多模态输入（文本 + 图片）

        Args:
            messages: 文本消息
            tooluse: 是否派发 tools schema + 是否允许 FC 续轮。默认 ``True``。
            addhistory: 是否把 user / assistant / tool_result 写入 history。
                设 ``False`` 可做"不计入对话"的一次性 AI 调用。
            images: 图片列表，可以是 base64 字符串或图片 URL
        """
        work_history = self.history

        if addhistory and messages:
            # 如果有图片，构建多模态内容
            if images:
                content_list = [{"type": "text", "text": messages}]
                for img in images:
                    if img.startswith("http"):
                        content_list.append({
                            "type": "image_url",
                            "image_url": {"url": img}
                        })
                    else:
                        # 假设是 base64
                        content_list.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img}"}
                        })
                work_history.append({"role": "user", "content": content_list})
            else:
                work_history.append({"role": "user", "content": messages})

        if self.fc_model and tooluse:
            # Function Calling 模式
            tools_schema = list(tool_registry.get_all_tools_schema(self.uuid))
            for s in tool_registry.collect_builtin_tools(self):
                tools_schema.append(s)
            try:
                from .skill import skill_registry
                tools_schema.extend(skill_registry.get_all_tool_schemas())
            except ImportError:
                pass
        else:
            tools_schema = []

        # 抽出 system（history[0]）→ ChatRequest.system
        if work_history and isinstance(work_history[0], dict) and work_history[0].get("role") == "system":
            system_str = work_history[0].get("content") or ""
            rest_messages = list(work_history[1:])
        else:
            system_str = ""
            rest_messages = list(work_history)

        req = ChatRequest(
            model=self.model_name,
            system=system_str,
            messages=rest_messages,
            tools=tools_schema,
            stream=self.stream,
        )

        # ---- 通过 transport 调 LLM ----
        transport = HttpxOpenAITransport(
            endpoint=self.api_provider,
            api_key=self.api_key,
        )

        full_content = ""
        tool_calls_list: list = []
        self.stream_run = True

        if self.stream:
            for evt in transport.chat_stream(req):
                if evt.type == "text":
                    full_content += evt.text
                    self.pack(evt.text, finish_task=False)
                elif evt.type == "tool_call" and evt.tool_call is not None:
                    tc = evt.tool_call
                    tool_calls_list.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    })
                elif evt.type == "usage" and evt.usage is not None:
                    self.stream_run = False
                    self.pack(finish_task=True)
                    self.pack(
                        f"\n本次请求用量：提示 {evt.usage.prompt_tokens} tokens，"
                        f"生成 {evt.usage.completion_tokens} tokens，"
                        f"总计 {evt.usage.total_tokens} tokens。",
                        other=True,
                    )
                # evt.type == "done" 不需要额外处理
        else:
            self.stream_run = False
            try:
                llm_rsp: LLMResponse = transport.chat(req)
                full_content = llm_rsp.text
                if full_content:
                    self.pack(full_content, finish_task=False)
                for tc in llm_rsp.tool_calls:
                    tool_calls_list.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    })
                if llm_rsp.usage is not None:
                    self.pack(finish_task=True)
                    self.pack(
                        f"\n本次请求用量：提示 {llm_rsp.usage.prompt_tokens} tokens，"
                        f"生成 {llm_rsp.usage.completion_tokens} tokens，"
                        f"总计 {llm_rsp.usage.total_tokens} tokens。",
                        other=True,
                    )
            except Exception as e:
                logger.error(f"非流式响应处理错误: {e}")
                full_content = ""

        logger.trace(f"AI 回复内容长度：{len(full_content)}")

        # Function Calling: 执行工具调用
        if tooluse and self.fc_model and tool_calls_list:
            logger.debug(f"发现 Function Calling 工具调用: {tool_calls_list}")

            # 添加 assistant message with tool_calls
            if addhistory:
                work_history.append({
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls_list
            })

            tool_results = []
            for tool_call in tool_calls_list:
                tool_name = tool_call['function']['name']
                tool_id = tool_call['id']

                # 查找工具
                tool_func = None
                if tool_registry.check_permission(self.uuid, tool_name):
                    tool_info = tool_registry.get_tool_info(tool_name)
                    if tool_info is not None:
                        tool_func = tool_info['function']

                if tool_func is None:
                    error_msg = f"找不到工具或无权限：'{tool_name}'"
                    logger.warning(error_msg)
                    tool_results.append({
                        'tool_call_id': tool_id,
                        'name': tool_name,
                        'content': error_msg
                    })
                    continue

                # 调用工具（解析 arguments 为 dict）
                try:
                    args = json.loads(tool_call['function']['arguments'])
                    # 生成任务 ID
                    self.current_task_id = self._generate_task_id()
                    # 执行 before 钩子
                    self._execute_hooks('before', tool_name, args)
                    logger.debug(f"调用工具 {tool_name}，参数: {args}")
                    self.pack(tool_name=tool_name, tool_parameter=args)

                    # Pydantic 校验（如果 @builtin_tool 提供了 params_model）
                    from .agent_tool import _validate_tool_args_for
                    args = _validate_tool_args_for(self, tool_name, args)

                    result, async_id = self._tool_runner.submit(
                        tool_func, tool_name=tool_name, timeout=self.tool_timeout, **args
                    )
                    if async_id is not None:
                        # 超时转后台：让 LLM 拿到 task_id 继续做别的
                        result = (
                            f"[tool {tool_name} still running in background as task_id={async_id}; "
                            f"check via self._tool_runner.get_status('{async_id}') "
                            f"or wait via self._tool_runner.wait('{async_id}')]"
                        )

                    # 执行 after 钩子
                    self._execute_hooks('after', tool_name, args, result)
                    # 打包工具返回值
                    self.pack(tool_result=result, tool_name=tool_name)
                    tool_results.append({
                        'tool_call_id': tool_id,
                        'name': tool_name,
                        'content': result
                    })
                except Exception as e:
                    error_msg = f"执行工具 {tool_name} 时出错: {str(e)}"
                    logger.error(error_msg)

                    # 执行 error 钩子（如果 args 已定义）
                    if 'args' in locals():
                        self._execute_hooks('error', tool_name, args, error_msg)
                    tool_results.append({
                        'tool_call_id': tool_id,
                        'name': tool_name,
                        'content': error_msg
                    })

            # 添加 tool responses 到历史
            for result in tool_results:
                if addhistory:
                    work_history.append({
                        "role": "tool",
                        "tool_call_id": result['tool_call_id'],
                        "name": result['name'],
                        "content": result['content']
                    })

            # 继续对话（无熔断；只受 attempt_completion / 用户主动结束影响）
            logger.debug("工具执行完成，继续对话")
            return self.conversation()

        # XML 模式：提取并执行工具
        xml_pattern = re.compile(r'<(\w+)>.*?</\1>', flags=re.S)
        clean_pattern = re.compile(r'</?(out_text|thinking)>', flags=re.S)
        clean_content = clean_pattern.sub('', full_content)
        xml_blocks = [m.group(0) for m in xml_pattern.finditer(clean_content)]

        tool_results = []
        tool_names = []
        for block in xml_blocks:
            logger.debug(f"发现工具块：{block[:50]}...")
            soup = BeautifulSoup(block, "xml")
            root = soup.find()
            if root is None:
                raise ValueError("空 XML")
            tool_name = root.name

            # 优先级查找工具：1. 工具注册器 2. 类方法 3. 返回无工具
            tool_func = None
            tool_source = None

            # 优先级1: 在工具注册器中查找
            if tool_registry.check_permission(self.uuid, tool_name):
                tool_info = tool_registry.get_tool_info(tool_name)
                if tool_info is not None:
                    tool_func = tool_info['function']
                    tool_source = "工具注册器"

            if tool_func is None:
                available_tools = self.get_all_available_tools()
                tool_error = f"工具错误：工具 '{tool_name}' 未注册或无权限。"
                if available_tools:
                    tool_error += f" 你可以使用以下工具：{', '.join(available_tools)}"
                work_history.append({"role": "system", "content": tool_error})
                tool_results.append({"error": tool_error})
                logger.warning(f"工具 {tool_name} 未注册或无权限，可用工具: {available_tools}")
                continue

            logger.debug(f"从 {tool_source} 找到工具 {tool_name}")
            print(block)

            # 解析 XML 参数，与 Function Calling 模式统一
            params = {}
            for child in root.children:
                if hasattr(child, 'name') and child.name:
                    params[child.name] = child.text

            # 生成任务 ID
            self.current_task_id = self._generate_task_id()

            # 执行 before 钩子
            self._execute_hooks('before', tool_name, params)

            self.pack(tool_name=tool_name, tool_parameter=params)

            # 执行工具：根据函数签名决定传递 dict 还是解包参数
            import inspect
            sig = inspect.signature(tool_func)
            param_count = len([p for p in sig.parameters.values()
                             if p.default == inspect.Parameter.empty and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)])

            # 如果函数接受 **kwargs 或单个参数，传递整个 dict
            # 否则解包参数
            has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            if has_kwargs or param_count == 0:
                result = tool_func(**params) if params else tool_func()
            elif param_count == 1 and len(params) == 1:
                # 单个参数函数，传递单个值
                result = tool_func(list(params.values())[0])
            else:
                # 多参数函数，尝试解包
                try:
                    result = tool_func(**params)
                except TypeError:
                    # 如果解包失败，回退到传递整个 XML 块（向后兼容）
                    result = tool_func(block)

            # 执行 after 钩子（传入结果）
            self._execute_hooks('after', tool_name, params, result)

            # 打包工具返回值
            self.pack(tool_result=result, tool_name=tool_name)

            if not result:
                result = f"no return for the tool{tool_name}"

            tool_results.append(result)
            tool_names.append(tool_name)

        #如配置错误强制跳出避免堵塞
        if "<attempt_completion>" in full_content:
            self.pack("\n[系统] AI 已标记任务完成，程序退出。", tool_name="attempt_completion")
            # sys.exit(0)

        # 3. 若工具产生结果，继续对话
        if tool_results:
            logger.debug(f"工具执行成功，结果数：{len(tool_results)}")
            n = 0
            for i in tool_results:
                try:
                    if addhistory:
                        work_history.append({"role": "system", "content": f"{tool_names[n]} results: {i}"})
                    n += 1
                except Exception:
                    break
            logger.debug(f"对话历史长度：{len(self.history)}")
            return self.conversation()
        # 递归到这（addhistory=True 默认路径）：本轮 LLM 已回应过，无新工具触发，
        # LLM 的回复 full_content 就是最终答案；不是 work_history[-1]（那是上轮 tool_result）。
        # v0.3.1 之前这里错把 work_history[-1] 当答案返回，导致多轮工具调用后
        # 同步路径直接吐出 tool_result，丢 LLM 的最终文本。
        return full_content

    @_auto_save
    def conversation_with_tool(self, messages=None, tool: bool = False, images=None):
        """**Deprecated** since v1.3.0; use :meth:`conversation` instead.

        行为等价于 ``self.conversation(messages, tooluse=True, addhistory=True, images=images)``。
        """
        _warnings.warn(
            "conversation_with_tool is deprecated since v1.3.0; "
            "use conversation(tooluse=True, addhistory=True) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.conversation(
            messages=messages, tooluse=True, addhistory=True, images=images,
        )

    @_auto_save_async
    async def aconversation(
        self,
        messages=None,
        *,
        tooluse: bool = True,
        addhistory: bool = True,
        images=None,
    ):
        """
        异步版 conversation（基于 transport.achat_stream）。

        用法::

            import asyncio
            result = asyncio.run(agent.aconversation("hi"))

        注意：tool_runner 仍是 ThreadPoolExecutor（同步执行工具），但
        LLM 调用走 async，事件循环不被阻塞。

        Args:
            messages: 字符串、消息 dict、消息 list
            tooluse  : 是否派发 tools schema + 是否允许 FC 续轮。默认 ``True``。
            addhistory: 是否把 user / assistant / tool_result 写入 history。
                设 ``False`` 可做"不计入对话"的一次性 AI 调用。
            images  : 图片 URL 或 base64
        """
        from .llm_transport import ChatRequest, HttpxOpenAITransport

        work_history = self.history

        if addhistory and messages is not None:
            if images:
                content_list = [{"type": "text", "text": messages}]
                for img in images:
                    if img.startswith("http"):
                        content_list.append({
                            "type": "image_url",
                            "image_url": {"url": img},
                        })
                    else:
                        content_list.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img}"},
                        })
                work_history.append({"role": "user", "content": content_list})
            else:
                work_history.append({"role": "user", "content": messages})

        if self.fc_model and tooluse:
            tools_schema = list(tool_registry.get_all_tools_schema(self.uuid))
            for s in tool_registry.collect_builtin_tools(self):
                tools_schema.append(s)
            try:
                from .skill import skill_registry
                tools_schema.extend(skill_registry.get_all_tool_schemas())
            except ImportError:
                pass
        else:
            tools_schema = []

        if work_history and isinstance(work_history[0], dict) and work_history[0].get("role") == "system":
            system_str = work_history[0].get("content") or ""
            rest_messages = list(work_history[1:])
        else:
            system_str = ""
            rest_messages = list(work_history)

        req = ChatRequest(
            model=self.model_name,
            system=system_str,
            messages=rest_messages,
            tools=tools_schema,
            stream=self.stream,
        )

        transport = HttpxOpenAITransport(endpoint=self.api_provider, api_key=self.api_key)
        full_content = ""
        tool_calls_list: list = []

        if self.stream:
            async for evt in transport.achat_stream(req):
                if evt.type == "text":
                    full_content += evt.text
                    self.pack(evt.text, finish_task=False)
                elif evt.type == "tool_call" and evt.tool_call is not None:
                    tc = evt.tool_call
                    tool_calls_list.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    })
                elif evt.type == "usage" and evt.usage is not None:
                    self.stream_run = False
                    self.pack(finish_task=True)
                    self.pack(
                        f"\nusage: prompt={evt.usage.prompt_tokens} "
                        f"completion={evt.usage.completion_tokens} "
                        f"total={evt.usage.total_tokens}",
                        other=True,
                    )
        else:
            self.stream_run = False
            llm_rsp = await transport.achat(req)
            full_content = llm_rsp.text
            if full_content:
                self.pack(full_content, finish_task=False)
            for tc in llm_rsp.tool_calls:
                tool_calls_list.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                })
            if llm_rsp.usage is not None:
                self.pack(finish_task=True)
                self.pack(
                    f"\nusage: prompt={llm_rsp.usage.prompt_tokens} "
                    f"completion={llm_rsp.usage.completion_tokens} "
                    f"total={llm_rsp.usage.total_tokens}",
                    other=True,
                )

        # FC 模式：执行 tool calls
        if tooluse and self.fc_model and tool_calls_list:
            if addhistory:
                work_history.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tool_calls_list,
                })
            tool_results: list = []
            for tool_call in tool_calls_list:
                tool_name = tool_call["function"]["name"]
                tool_id = tool_call["id"]
                try:
                    args = json.loads(tool_call["function"]["arguments"])
                    from .agent_tool import _validate_tool_args_for
                    args = _validate_tool_args_for(self, tool_name, args)
                    self.current_task_id = self._generate_task_id()
                    self._execute_hooks("before", tool_name, args)
                    self.pack(tool_name=tool_name, tool_parameter=args)
                    async_id = None
                    result, async_id = self._tool_runner.submit(
                        tool_func=self._resolve_tool(tool_name),
                        tool_name=tool_name,
                        timeout=self.tool_timeout,
                        **args,
                    )
                    if async_id is not None:
                        result = (
                            f"[tool {tool_name} still running in background as task_id={async_id}]"
                        )
                    self._execute_hooks("after", tool_name, args, result)
                    self.pack(tool_result=result, tool_name=tool_name)
                    tool_results.append({
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": result,
                    })
                except Exception as e:
                    error_msg = f"tools execution failed: {e}"
                    logger.error(error_msg)
                    self._execute_hooks("error", tool_name, args, error_msg)
                    tool_results.append({
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": error_msg,
                    })
            for result in tool_results:
                if addhistory:
                    work_history.append({
                        "role": "tool",
                        "tool_call_id": result["tool_call_id"],
                        "name": result["name"],
                        "content": result["content"],
                    })
            return await self.aconversation()

        return full_content

    @_auto_save_async
    async def aconversation_with_tool(self, messages=None, tool: bool = False, images=None):
        """**Deprecated** since v1.3.0; use :meth:`aconversation` instead.

        行为等价于 ``await self.aconversation(messages, tooluse=True, addhistory=True, images=images)``。
        """
        _warnings.warn(
            "aconversation_with_tool is deprecated since v1.3.0; "
            "use aconversation(tooluse=True, addhistory=True) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.aconversation(
            messages=messages, tooluse=True, addhistory=True, images=images,
        )

    def _resolve_tool(self, name: str):
        """解析 tool 名字到实际 callable"""
        tool_func = None
        if tool_registry.check_permission(self.uuid, name):
            info = tool_registry.get_tool_info(name)
            if info is not None:
                tool_func = info["function"]
        if tool_func is None:
            raise ValueError(f"工具未注册或无权限：{name}")
        return tool_func

    def pack(self, message=None, tool_model=False, tool_name=None, tool_parameter=None,
             finish_task=False, other=False, tool_result=None) -> None:
        """
        打包输出内容，包含 AI UUID、任务戳和时间戳

        参数:
            message: 普通消息内容
            tool_model: 是否是工具模型调用
            tool_name: 工具名称
            tool_parameter: 工具参数
            finish_task: 是否任务完成
            other: 其他标记
            tool_result: 工具执行结果

        注意:
            ``pack`` 的职责只是把"事件"打包成 dict 然后交给 ``self.out(content)``。
            如果你的目标是**接管输出行为**（流式 / UI / 自定义 logger / 静默等），
            请覆写 ``out``，不要覆写 ``pack``。
            框架在子类覆写 ``pack`` 但未覆写 ``out`` 时会在构造时给出一条 warning。
        """
        content = {}
        task_id = self.current_task_id or self._generate_task_id()
        timestamp = self._get_timestamp()

        if finish_task:
            content = {
                "task": True,
                "task_id": task_id,
                "timestamp": timestamp,
                "ai_uuid": self.uuid,
                "ai_name": self.name
            }
        elif tool_model:
            content = {
                "tool_name": tool_name,
                "tool_parameter": tool_parameter,
                "ai_uuid": self.uuid,
                "ai_name": self.name,
                "task_id": task_id,
                "timestamp": timestamp,
                "task": False
            }
        elif tool_result is not None:
            # 工具返回值
            content = {
                "tool_result": tool_result,
                "tool_name": tool_name,
                "ai_uuid": self.uuid,
                "ai_name": self.name,
                "task_id": task_id,
                "timestamp": timestamp,
                "task": False
            }
        else:
            content = {
                "message": message,
                "ai_uuid": self.uuid,
                "ai_name": self.name,
                "other": other,
                "task_id": task_id,
                "timestamp": timestamp,
                "task": False
            }
        self.out(content)

    def out(self, content: dict) -> None:
        if content.get("tool_name"):
            print("调用工具:", content.get("tool_name"), "参数", content.get("tool_parameter"))
            return
        if not content.get("task"):
            message = content.get("message")
            if message is not None:
                print(message, end="")
        else:
            print()


    # ---------------- 内置工具（@builtin_tool 装饰器自动从签名推导 schema）----------------

    @builtin_tool(
        description="请求其他Agent帮助",
        params={
            "agent_id": "目标Agent的UUID或名称",
            "message": "请求内容",
        },
    )
    def ask_for_help(self, agent_id: str, message: str) -> str:
        """请求另一个 Agent 协助完成子任务，并把对方的回复作为工具返回值返回。

        走全局队列：避免递归栈过深 / 循环调用自动超时。
        - 循环检测：若 target 在当前调用链里直接拒绝
        - 深度限制：链长达到 max_depth 也直接拒绝
        - 串行执行：worker pool 中每个 worker 一次只跑一个 Job
        """
        from .agent_queue import get_call_chain, get_default_queue

        try:
            from tangyuanAI import agent_list

            target = agent_list.get(agent_id)
            if target is None:
                # 接受 UUID 或 name 两种引用
                target = next(
                    (a for a in agent_list.values() if a.name == agent_id),
                    None,
                )
            if target is None:
                return f"未找到 Agent：{agent_id}"

            chain = get_call_chain()
            queue = get_default_queue()
            return queue.submit(
                target_uuid=target.uuid,
                call_fn=lambda: str(target.conversation(message)),
                caller_chain=chain,
            )
        except Exception as e:
            logger.error(f"ask_for_help 失败：{e}")
            return f"协助请求失败：{e}"

    @builtin_tool(
        description="列出所有可用的Agent及其UUID和名称",
    )
    def list_agents(self) -> str:
        """返回当前系统中所有已注册 Agent 的清单，便于发现协作对象。"""
        from tangyuanAI import agent_list

        unique_agents: dict = {}
        for _key, inst in agent_list.items():
            inst_uuid = getattr(inst, "uuid", None)
            inst_name = getattr(inst, "name", None)
            inst_desc = getattr(inst, "description", None)
            if inst_uuid and inst_name and inst_uuid not in unique_agents:
                unique_agents[inst_uuid] = {
                    "uuid": inst_uuid,
                    "name": inst_name,
                    "description": inst_desc,
                }

        if not unique_agents:
            return "可用的Agent列表：（暂无）"

        lines = []
        for info in unique_agents.values():
            lines.append(
                f"- {info['name']} (UUID: {info['uuid']}) description: {info['description']}"
            )
        return "可用的Agent列表：" + "".join(lines)

    @builtin_tool(
        description="标记任务完成并退出",
        params={"report_content": "汇报内容（可空）"},
    )
    def attempt_completion(self, report_content: str = "") -> str:
        """告知框架当前任务已结束，传入汇报内容；该工具返回值即为整个任务的对外输出。"""
        return report_content if report_content else "任务已完成"

    @builtin_tool(
        description="重新加载你自己：重新拉取当前可用的工具列表和Skills，重置系统提示词。",
    )
    def reload(self) -> str:
        """重新构建内部状态（系统提示词 / 工具列表 / Skills），保留对话历史。"""
        self.__init__(new_load=False)
        return "successfully reloaded"

    # ---------------- 模板池工具（register_template / activate_template / deactivate_template / list_templates）----------------

    @builtin_tool(
        description="把一个 Agent 类（cls）注册进 agent_template_pool，**不实例化**。",
        params={
            "name": "模板名（池内唯一标识）",
            "description": "可选：模板描述",
        },
    )
    def register_template(self, name: str, description: str = "") -> str:
        """占位说明：工具调用只能传 JSON，Python 类对象无法经由工具参数传入，
        因此模板注册必须在 Python 代码侧完成。本工具不修改 agent_template_pool。"""
        from .Agent_list import list_templates as _list_templates
        items = _list_templates()
        if not items:
            return (
                "模板注册请在 Python 代码侧完成："
                "from tangyuanAI.Agent_list import register_template;"
                "register_template(MyAgent, name='my_agent'。"
                "当前 agent_template_pool 为空。"
            )
        names = "、".join(it["name"] for it in items)
        return (
            "模板注册请在 Python 代码侧完成："
            "from tangyuanAI.Agent_list import register_template;"
            "register_template(MyAgent, name='my_agent'。"
            f"当前 agent_template_pool 内的模板：{names}。"
        )

    @builtin_tool(
        description="把 agent_template_pool 中的某个模板实例化并写入 agent_list。",
        params={"name": "模板名"},
    )
    def activate_template(self, name: str) -> str:
        """显式激活模板：把模板池中的类实例化，写入 agent_list。"""
        from .Agent_list import activate_template
        try:
            activate_template(name)
        except KeyError as e:
            return f"激活失败：{e}"
        return (
            f"已激活模板 {name!r}：实例已写入 agent_list。"
            f"可通过 agent_list[{name!r}] 或其 uuid 访问。"
        )

    @builtin_tool(
        description="把 agent_list 中的某个模板实例移除（模板仍保留在池中）。",
        params={"name": "模板名"},
    )
    def deactivate_template(self, name: str) -> str:
        """从 agent_list 移除实例，模板仍保留在 agent_template_pool。"""
        from .Agent_list import deactivate_template
        ok = deactivate_template(name)
        return f"已反激活 {name!r}" if ok else f"模板 {name!r} 不在池中"

    @builtin_tool(
        description="查询 agent_template_pool 中的模板清单（只读，不会实例化）。",
        params={
            "name": "可选：模板名；为空则列出全部",
        },
    )
    def list_templates(self, name: str = "") -> str:
        """查看模板池 + 激活状态。可选 name 过滤单个模板。"""
        from .Agent_list import (
            agent_list,
            get_template,
        )
        from .Agent_list import (
            list_templates as _list_templates,
        )
        if name:
            tpl = get_template(name)
            if tpl is None:
                return f"模板 {name!r} 不在 agent_template_pool 中"
            return (
                f"模板 {name!r}: uuid={tpl.get('uuid')!r}, "
                f"description={tpl.get('description')!r}, "
                f"active={name in agent_list}"
            )
        items = _list_templates()
        if not items:
            return "agent_template_pool：（暂无）"
        lines = []
        for it in items:
            lines.append(
                f"- {it['name']} (uuid={it['uuid']}) "
                f"active={it['active']} description={it.get('description')!r}"
            )
        return "agent_template_pool：\n" + "\n".join(lines)

    def get_all_available_tools(self) -> list:
        tools: list[Any] = []
        tools_info = tool_registry.get_all_tools_info(self.uuid)
        if tools_info:
            tools.extend(tools_info.keys())
        for s in tool_registry.collect_builtin_tools(self):
            tools.append(s["function"]["name"])
        return tools



