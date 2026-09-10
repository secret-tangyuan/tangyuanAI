# -*- coding: utf-8 -*-
"""
tangyuanAI - 多智能体协作框架
=============================

基于 LLM 的轻量级多智能体协作系统框架，支持 OpenAI 兼容协议与 Anthropic 协议。

快速开始
--------

    import tangyuanAI
    from dotenv import load_dotenv
    load_dotenv()  # API_KEY 放在 .env

    @tangyuanAI.template_agent("my_agent", uuid="uuid-1", description="")
    class MyAgent(tangyuanAI.BaseAgent):
        prompt = "你是一个助手"
        api_provider = "https://api.example.com/v1/chat/completions"
        model_name = os.getenv("OPENAI_MODEL")
        api_key = os.getenv("OPENAI_API_KEY")

    agent = tangyuanAI.agent_list["my_agent"]
    agent.conversation_with_tool("你好")

Anthropic 协议用法::

    @tangyuanAI.template_agent("claude_agent", uuid="uuid-2", description="")
    class ClaudeAgent(tangyuanAI.Agent):
        protocol = "anthropic"
        prompt = "你是一个助手"
        model_name = os.getenv("ANTHROPIC_MODEL")
        api_key = os.getenv("ANTHROPIC_API_KEY")        # 可指向任意兼容端点（详见 AnthropicAgent docstring）

    tangyuanAI.agent_list["claude_agent"].conversation_with_tool("你好")

切协议只需改 ``protocol`` 字段（``"openai"`` / ``"anthropic"``），无需换基类。
详见 ``Agent`` docstring。

核心导出
--------

- ``register_agent`` : 手动注册 agent 实例到 agent_list（v0.4.2+）
- ``unregister_agent`` : 从 agent_list 注销（v0.4.2+）
- ``tool_registry``  : 工具注册器实例（@tool_registry.register_tool）
- ``Agent``          : **协议无关的 Agent 工厂基类**（用 ``protocol`` 字段选 openai / anthropic）
- ``BaseAgent``      : Agent 基类（OpenAI 协议，直接继承时使用）
- ``agent_list``     : 已注册 Agent 字典（按 UUID / 名称索引）
- ``anthropic_agent.AnthropicAgent`` : Anthropic 协议 Agent 基类（直接继承时使用）
- ``mcp_bridge``     : MCP 服务器集成（register_mcp_tools 等）
- ``skill``          : Agent Skills 开放标准集成

更多资源
--------

- 完整文档：https://github.com/secret-tangyuan/tangyuanAI/wiki
- 示例代码：examples/ 目录
- 发布流程：仓库根目录 RELEASING.md
- 许可证：Apache License 2.0
"""

from .agent import (
    ANTHROPIC,
    OPENAI,
    OPENAI_RESPONSES,
    Agent,
    AnthropicAgent,  # noqa: F401  (re-exported in __all__)
    BaseAgent,  # noqa: F401  (re-exported in __all__)
    agent,  # noqa: F401  (lowercase alias, re-exported)
    anthropic,  # noqa: F401  (lowercase alias, re-exported)
    list_protocols,  # noqa: F401
    openai,  # noqa: F401  (lowercase alias, re-exported)
    openai_responses,  # noqa: F401  (lowercase alias, re-exported)
    register_protocol,  # noqa: F401
)
from .Agent_list import (
    activate_template,
    agent_list,
    agent_source,
    agent_template_pool,
    deactivate_template,
    get_template,
    is_active,
    list_agents_with_source,
    list_external_agents,
    list_internal_agents,
    list_templates,
    register_agent,
    register_template,
    remove_template,
    template_agent,
    unregister_agent,
)
from .agent_tool import builtin_tool, tool_registry  # noqa: F401  (re-exported)

# 从 mcp_bridge 导入 MCP 相关功能
try:
    from .mcp_bridge import (
        close_all_mcp_sessions,
        close_all_mcp_sessions_sync,
        close_mcp_session,
        close_mcp_session_sync,
        get_session_info,
        mcp_session_context,
        register_mcp_tools,
        register_mcp_tools_async,
        start_health_check,
        stop_health_check,
    )
except ImportError:
    # mcp 未安装时提供兼容性
    pass

# 从 skill 导入 Skill 相关功能
# 插件协议 / 加载器（v1.1.0+）：KB 与图片生成由插件包提供，这里只暴露协议与发现 API
from .plugin_api import PluginEntry, PluginError  # noqa: F401  (re-exported)
from .plugin_loader import (  # noqa: F401  (re-exported)
    discover_plugins,
    get_plugin_api,
    get_plugin_api_by_type,
    install_module_alias,
    load_external_plugin,
    load_plugin,
    plugin_available,
    plugin_installed,
)
from .skill import Skill, skill_registry
from .skill_bridge import register_skill_as_tool, unregister_skill_from_tool

# A2A 兼容层（v1.0.0+，核心原生支持；导入 = 客户端，导出 = aiohttp server，均守卫）
try:
    from .a2a_client import (
        A2AAgentProxy,
        discover,
        register_a2a_agent,
        send_task,
        send_task_sync,
    )
    from .a2a_exporter import A2AExporter
    from .a2a_protocol import (
        extract_text_from_artifacts,
        make_agent_card,
        make_json_rpc_request,
        make_json_rpc_response,
        make_text_message,
    )
except ImportError:
    pass

# MCP 客户端类（#5 类化）
try:
    from .mcp_client import MCPClient
except ImportError:
    pass

# Image Generation（config-driven）
try:
    from .imaging import (
        HttpJsonImageProvider,
        ImageError,
        ImageGenerator,
        ImageProvider,
        download_urls,
        render_template,
        resolve_json_path,
        resolve_url_template,
    )
    from .plugin_store import install_plugin, list_installed
except ImportError:
    pass

# 从 kb 包导入 KB 相关功能（MCP 风格守卫 import）
try:
    from .kb import (
        Chunk,
        Chunker,
        DocMeta,
        DocProcessor,
        Document,
        Embedder,
        EmbedderConfig,
        Knowledge,
        KnowledgeBase,
        Loader,
        LRUDiskCache,
        NullCache,
        Reranker,
        RerankerConfig,
        ScoreKind,
        SearchResult,
        VectorStore,
        Visibility,
        add_document,
        add_document_sync,
        add_documents,
        add_documents_sync,
        create_chunker,
        create_embedder,
        create_loader,
        create_reranker,
        delete_kb,
        get_global_cache,
        get_kb,
        get_processor_for,
        list_chunkers,
        list_doc_processors,
        list_documents,
        list_documents_sync,
        list_embedder_providers,
        list_kbs,
        list_loaders,
        list_reranker_providers,
        migrate_embedding_model,
        migrate_embedding_model_sync,
        register_kb,
        register_kb_tools,
        search,
        search_sync,
        set_global_cache,
        shutdown_kb,
        unregister_kb_tools,
    )
except ImportError:
    pass

# 版本号自动从包元数据读取，与 tangyuanAI/pyproject.toml 中的 version 字段保持同步。
# 覆盖方式（仅在打包失败等极端场景下使用）：import tangyuanAI; tangyuanAI.__version__ = "x"
try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    try:
        __version__ = _pkg_version("tangyuanAI")
    except PackageNotFoundError:
        # 包未安装（极少见，例如源码直接以脚本运行）
        __version__ = "0.0.0+unknown"
except Exception:  # pragma: no cover
    __version__ = "0.0.0+unknown"

__author__ = "secret-tangyuan"


# ======================================================================
# 协议无关的 Agent 工厂：``Agent`` + ``protocol`` 字段自动选基类
# ======================================================================
#
# 旧版在 __init__.py 里定义了 _ProtocolMeta + Agent 占位类。
# v0.4.2+：已合并进 agent.py（agent.Agent / agent.BaseAgent / agent.AnthropicAgent）。
# 这里只 re-export，不再重复定义 metaclass 或 Agent 类 —— 避免重复分发。

# Agent / BaseAgent / AnthropicAgent 自上（agent.py）import，见文件顶部。


__all__ = [
    # 核心组件
    "register_agent",       # 手动注册 API（v0.4.2+）
    "unregister_agent",     # 手动注销 API（v0.4.2+）
    "agent_source", "list_internal_agents", "list_external_agents", "list_agents_with_source",  # 来源跟踪（v1.0.0+）
    "template_agent",       # 模板池装饰器（v0.3.0+ 推荐）
    # 插件协议 / 加载器（v1.1.0+）
    "discover_plugins", "plugin_installed", "plugin_available", "load_plugin",
    "load_external_plugin",   # v1.1.1+ OpenAI / Anthropic plugin manifest 加载
    "get_plugin_api", "get_plugin_api_by_type", "install_module_alias",
    "PluginEntry", "PluginError",
    "activate_template",    # 模板池激活（v0.3.0+）
    "deactivate_template",  # 模板池反激活（v0.3.0+）
    "register_template",    # 函数式入池（v0.3.0+）
    "remove_template",      # 彻底从池中删除
    "list_templates",       # 列出全部模板
    "get_template",         # 查单个模板
    "is_active",            # 模板是否已激活
    "agent_template_pool",  # 模板池 dict
    "tool_registry",
    "Agent",          # 协议无关的工厂基类（推荐）
    "BaseAgent",      # OpenAI 协议基类（直接继承时用）
    "agent_list",
    # 协议常量（v0.4.2+）：agent.protocol = OPENAI 无需打引号
    "OPENAI",
    "ANTHROPIC",
    "OPENAI_RESPONSES",
    "openai",
    "anthropic",
    "openai_responses",
    # MCP 功能
    "register_mcp_tools",
    "register_mcp_tools_async",
    "close_mcp_session",
    "close_mcp_session_sync",
    "close_all_mcp_sessions",
    "close_all_mcp_sessions_sync",
    "get_session_info",
    "start_health_check",
    "stop_health_check",
    "mcp_session_context",
    # Skill 功能
    "skill_registry",
    "Skill",
    "register_skill_as_tool",
    "unregister_skill_from_tool",
    # MCP 客户端类（v1.0.0+）
    "MCPClient",
    # Image Generation（config-driven，v1.0.0+）
    "ImageGenerator", "ImageProvider", "ImageError", "HttpJsonImageProvider",
    "download_urls", "install_plugin", "list_installed",
    "resolve_json_path", "render_template", "resolve_url_template",
    # A2A 兼容（v1.0.0+）
    "A2AExporter", "A2AAgentProxy",
    "discover", "register_a2a_agent", "send_task", "send_task_sync",
    "make_agent_card", "make_text_message",
    "make_json_rpc_request", "make_json_rpc_response",
    "extract_text_from_artifacts",
    # 持久化（v0.3.2+）
    "save_state",
    "load_state",
    "delete_state",
    "list_states",
    "export_state_string",
    "load_state_string",
    "register_backend",
    "set_default_backend",
    "configure",         # 程序化配置自动持久化
    "is_enabled",        # 当前是否启用了自动持久化
    "disable",           # 关闭自动持久化
    "auto_save",         # 手动触发一次自动保存
    "FileBackend",       # 内置 file 后端（默认）
    "SQLiteBackend",     # 内置 sqlite 后端（实验性）
    "AgentNotFoundError",  # load_state 找不到类时抛
    "FormatError",       # 状态文件格式错误时抛
    # Knowledge Base（v1.0.0+）
    "Knowledge", "KnowledgeBase", "Chunk", "Document", "DocMeta", "SearchResult",
    "ScoreKind", "Visibility",
    "EmbedderConfig", "RerankerConfig",
    "Embedder", "Reranker", "VectorStore", "Chunker", "DocProcessor", "Loader",
    "LRUDiskCache", "NullCache", "get_global_cache", "set_global_cache",
    "register_kb", "get_kb", "list_kbs", "delete_kb",
    "add_document", "add_document_sync", "add_documents", "add_documents_sync",
    "shutdown_kb",
    "search", "search_sync", "list_documents", "list_documents_sync",
    "migrate_embedding_model", "migrate_embedding_model_sync",
    "register_kb_tools", "unregister_kb_tools",
    "create_embedder", "create_reranker", "create_chunker", "create_loader",
    "get_processor_for",
    "list_embedder_providers", "list_reranker_providers",
    "list_chunkers", "list_loaders", "list_doc_processors",
    # 元信息
    "__version__",
    "__author__",
]


# 持久化 API 顶层导出（v0.3.2+）
# 在 import 时读取环境变量配置自动持久化
from .persistence import (  # noqa: E402
    AgentNotFoundError,
    FileBackend,
    FormatError,
    SQLiteBackend,
    _read_env_config,  # noqa: E402
    auto_save,
    configure,
    delete_state,
    disable,
    export_state_string,
    is_enabled,
    list_states,
    load_state,
    load_state_string,
    register_backend,
    save_state,
    set_default_backend,
)

_read_env_config()


def help():
    """在终端打印帮助信息。

    内容由两部分拼装，**全部自动生成，无硬编码字符串**：

    1. **静态文档**：直接 ``print(__doc__)``（即模块顶部 docstring）。
       改 docstring 一次，``help()`` 输出自动跟着改。
    2. **运行时状态**：从 ``agent_list`` / ``tool_registry`` 反射当前已注册的对象。
       不需要手动维护"当前已注册 Agent 列表"之类的字符串。

    Windows 终端自动切换到 UTF-8 编码，避免中文乱码。
    """
    import sys
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    # 1) 静态文档：模块 docstring
    print(__doc__)

    # 2) 运行时状态（反射当前已注册的 Agent / 工具）
    print(f"\n运行时状态（v{__version__}）")
    print("-" * 60)
    n_agents = len(agent_list)
    if n_agents:
        names = sorted(agent_list.keys())
        print(f"已注册 Agent: {n_agents} 个 → {', '.join(names)}")
    else:
        print("已注册 Agent: 0 个（请用 @tangyuanAI.template_agent 注册）")

    try:
        tools = list(tool_registry.list_tools() or [])
    except Exception:  # pragma: no cover
        tools = []
    if tools:
        print(f"已注册工具: {len(tools)} 个 → {', '.join(sorted(tools))}")
    else:
        print("已注册工具: 0 个（请用 @tool_registry.register_tool 注册）")

    # 3) 命令行入口提示（指向真实模块，不写死字符串）
    try:
        import tangyuanAI.cli as _cli
        cli_module = _cli.__name__
    except Exception:  # pragma: no cover
        cli_module = "tangyuanAI"
    print("\n命令行入口：")
    print(f"  $ python -m {cli_module} --help    # 全部子命令")
    print(f"  $ python -m {cli_module} --doctor  # 环境自检（Python / API Key / 已注册 Agent）")
    print(f"  $ python -m {cli_module} --demo    # 离线 demo（不连真实 LLM）")


# 方便交互式访问：``help(tangyuanAI)`` 会显示模块 docstring
help.__doc__ = __doc__
