"""tangyuanAI protocol chain —— v1.4.0 引入的多 provider fallback transport。

设计目标:
- 一个 agent 在 `protocol_chain=["openai", "anthropic", "openai-responses"]` 下自动 fallback
- 主 provider 失败(APIError / TimeoutError / ConnectionError)→ 下一个
- 全失败 → 抛 AllProvidersFailed
- streaming 半途失败:已 emit 的 chunk 不补,直接 raise

默认不启用,需在 `tangyuanai_config.json` 的 `protocol_chain` feature 里配。
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Iterator, List

from .errors import APIError
from .llm_transport import (
    ChatRequest,
    LLMEvent,
    LLMResponse,
    LLMTransport,
)

_logger = logging.getLogger(__name__)


class AllProvidersFailed(Exception):
    """所有 provider 都失败时抛出,内部保留每个 provider 的最后异常。"""

    def __init__(self, errors: list):
        self.errors = errors
        super().__init__(
            f"all {len(errors)} providers failed: " + "; ".join(str(e) for e in errors)
        )


class ProtocolChainTransport(LLMTransport):
    """try-chain 包装器。"""

    def __init__(self, chain: List[LLMTransport], provider_names: List[str] | None = None):
        if not chain:
            raise ValueError("ProtocolChainTransport 需要至少一个 transport")
        self.chain = chain
        # provider_names 用于日志/错误消息;缺省用对象 repr
        self.provider_names = provider_names or [str(t) for t in chain]

    def chat(self, req: ChatRequest) -> LLMResponse:
        errors = []
        for transport, name in zip(self.chain, self.provider_names):
            try:
                return transport.chat(req)
            except (APIError, TimeoutError, ConnectionError, OSError) as e:
                _logger.warning(f"protocol_chain: provider {name!r} 失败 ({type(e).__name__}: {e}),尝试下一个")
                errors.append(e)
        raise AllProvidersFailed(errors)

    async def achat(self, req: ChatRequest) -> LLMResponse:
        errors = []
        for transport, name in zip(self.chain, self.provider_names):
            try:
                return await transport.achat(req)
            except (APIError, TimeoutError, ConnectionError, OSError) as e:
                _logger.warning(f"protocol_chain: provider {name!r} 失败 ({type(e).__name__}: {e}),尝试下一个")
                errors.append(e)
        raise AllProvidersFailed(errors)

    def chat_stream(self, req: ChatRequest) -> Iterator[LLMEvent]:
        # stream 不 fallback:已 emit 的 chunk 不可补,直接 raise
        return self.chain[0].chat_stream(req)

    async def achat_stream(self, req: ChatRequest) -> AsyncIterator[LLMEvent]:
        return await self.chain[0].achat_stream(req) if False else self.chain[0].achat_stream(req)


__all__ = ["ProtocolChainTransport", "AllProvidersFailed"]
