"""tangyuanAI judge —— v1.4.0 引入的 LLM-as-judge。

用便宜 model (haiku / gpt-4o-mini) 对 agent 输出打分。
不用新依赖,直接走现有 transport。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional, Tuple

_logger = logging.getLogger(__name__)


@dataclass
class JudgeConfig:
    model: str = "gpt-4o-mini"           # 默认用便宜模型
    api_provider: Optional[str] = None
    api_key: Optional[str] = None
    protocol: str = "openai"
    system_prompt: str = (
        "你是一个严格的评测员。给定 prompt + agent 回复 + 评分标准,"
        "先输出 1-3 句推理,然后输出 PASS 或 FAIL (单独一行)。"
    )


class LLMJudge:
    """LLM-as-judge。

    用 JudgeConfig.model 跑一个简单 chat,问 PASS/FAIL + 推理。
    """

    def __init__(self, config: Optional[JudgeConfig] = None):
        self.config = config or JudgeConfig()

    def judge(self, prompt: str, response: str, criteria: str) -> Tuple[Optional[str], str]:
        """返 (verdict, reasoning)。

        verdict: "pass" / "fail" / None(解析失败)
        reasoning: LLM 给的 1-3 句推理
        """
        user_msg = (
            f"## prompt\n{prompt}\n\n"
            f"## agent 回复\n{response}\n\n"
            f"## 评分标准\n{criteria}"
        )
        try:
            from .llm_transport import ChatRequest, HttpxOpenAITransport, LLMResponse
            transport = HttpxOpenAITransport(
                endpoint=self.config.api_provider or "https://api.openai.com/v1",
                api_key=self.config.api_key or "",
            )
            req = ChatRequest(
                model=self.config.model,
                system=self.config.system_prompt,
                messages=[{"role": "user", "content": user_msg}],
                tools=None,
                stream=False,
                temperature=0,
            )
            rsp: LLMResponse = transport.chat(req)
            text = rsp.text or ""
            return self._parse(text)
        except Exception as e:
            _logger.warning(f"LLMJudge 失败: {e}")
            return None, f"judge error: {e}"

    @staticmethod
    def _parse(text: str) -> Tuple[Optional[str], str]:
        # 取最后一行非空文本;期望 PASS / FAIL
        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        if not lines:
            return None, ""
        verdict_raw = lines[-1].strip().upper()
        # 允许 "VERDICT: PASS" 之类
        verdict_raw = re.sub(r"^(VERDICT|JUDGMENT|RESULT)\s*[:\-]?\s*", "", verdict_raw).strip()
        if "PASS" in verdict_raw and "FAIL" not in verdict_raw:
            verdict = "pass"
        elif "FAIL" in verdict_raw:
            verdict = "fail"
        else:
            verdict = None
        reasoning = "\n".join(lines[:-1]).strip()
        return verdict, reasoning


__all__ = ["LLMJudge", "JudgeConfig"]