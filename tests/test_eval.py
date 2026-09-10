"""eval + judge 单元测试。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import pytest

from tangyuanAI.eval import (
    EvalCase,
    EvalResult,
    EvalSuite,
    render_table,
    run_case,
    run_suite,
)
from tangyuanAI.judge import JudgeConfig, LLMJudge


# ============================================================
# EvalCase / run_case
# ============================================================


class FakeAgent:
    """测试用 agent:conversation 直接给预定义回复,history 也预填。"""

    def __init__(self, response: str = "ok", history: list = None):
        self._response = response
        self.history = list(history or [])

    def conversation(self, prompt):
        # 模拟把 user msg 加进 history
        self.history.append({"role": "user", "content": prompt})
        self.history.append({"role": "assistant", "content": self._response, "tool_calls": []})
        return self._response


def test_keyword_match_default_passes_when_no_keywords():
    from tangyuanAI.eval import _keyword_match
    h, t = _keyword_match("anything", [])
    assert h == 0 and t == 0


def test_keyword_match_counts_hits():
    from tangyuanAI.eval import _keyword_match
    h, t = _keyword_match("北京今天晴天", ["北京", "今天", "雨"])
    assert h == 2
    assert t == 3


def test_tool_match_no_expected_full_score():
    from tangyuanAI.eval import _tool_match
    score, _ = _tool_match([{"name": "x"}], [])
    assert score == 1.0


def test_tool_match_exact_subset():
    from tangyuanAI.eval import _tool_match
    score, _ = _tool_match(
        [{"name": "get_weather"}, {"name": "send_email"}],
        ["get_weather"],
    )
    assert score == 1.0


def test_tool_match_partial():
    from tangyuanAI.eval import _tool_match
    score, _ = _tool_match(
        [{"name": "get_weather"}],
        ["get_weather", "send_email"],
    )
    assert score == 0.5


def test_run_case_with_keywords_and_tools():
    agent = FakeAgent(
        response="北京今天晴",
        history=[
            {"role": "user", "content": "天气?"},
            {"role": "assistant", "content": "北京今天晴", "tool_calls": [{"name": "get_weather"}]},
        ],
    )
    case = EvalCase(
        name="weather",
        prompt="北京天气?",
        expected_keywords=["北京", "今天"],
        expected_tool_calls=["get_weather"],
    )
    # 让 FakeAgent 在新加的 assistant 消息上也带 tool_calls,跑 run_case 取最后一条
    orig_conversation = agent.conversation

    def patched_conversation(prompt):
        agent.history.append({"role": "user", "content": prompt})
        agent.history.append({"role": "assistant", "content": agent._response, "tool_calls": [{"name": "get_weather"}]})
        return agent._response

    agent.conversation = patched_conversation

    r = run_case(agent, case)
    assert r.case_name == "weather"
    assert r.keyword_hits == 2
    assert r.keyword_total == 2
    assert r.tool_match == 1.0
    # kw 2/2=1.0 * 0.5 + tool 1.0 * 0.5 = 1.0
    assert r.pass_rate == 1.0


def test_run_case_missing_keyword():
    agent = FakeAgent(response="上海今天晴")
    case = EvalCase(name="x", prompt="?", expected_keywords=["北京"])
    r = run_case(agent, case)
    assert r.keyword_hits == 0
    assert r.keyword_total == 1
    # kw 0/1 * 0.5 + tool 1.0(no expected)* 0.5 = 0 + 0.5 = 0.5
    assert r.pass_rate == 0.5


def test_run_case_error_recorded_not_raised():
    class BoomAgent:
        def conversation(self, prompt):
            raise RuntimeError("llm down")

    case = EvalCase(name="boom", prompt="?")
    r = run_case(BoomAgent(), case)
    assert r.error is not None
    assert "RuntimeError" in r.error
    assert r.response == ""


def test_run_suite_resets_history_between_cases():
    case1 = EvalCase(name="a", prompt="?")
    case2 = EvalCase(name="b", prompt="?")
    factory_calls = []

    def factory():
        factory_calls.append(object())
        return FakeAgent("ok")

    suite = EvalSuite(name="t", agent_factory=factory, cases=[case1, case2])
    results = run_suite(suite)
    assert len(results) == 2
    assert len(factory_calls) == 2


def test_render_table_no_results(capsys):
    """空 results 不抛、打印 (no results)。"""
    import sys
    render_table([])
    out = capsys.readouterr().out
    assert "(no results)" in out


def test_render_table_with_results(capsys):
    """有 results 时打印表 + summary。"""
    agent = FakeAgent(
        response="北京今天晴",
        history=[
            {"role": "user", "content": "?"},
            {"role": "assistant", "content": "北京今天晴", "tool_calls": [{"name": "get_weather"}]},
        ],
    )
    case = EvalCase(name="weather", prompt="?", expected_keywords=["北京"], expected_tool_calls=["get_weather"])
    result = run_case(agent, case)
    render_table([result])
    out = capsys.readouterr().out
    assert "case" in out  # 表头
    assert "weather" in out  # case name
    assert "summary" in out  # 汇总行


# ============================================================
# LLMJudge 解析
# ============================================================


def test_judge_parse_pure_pass():
    v, r = LLMJudge._parse("agent answered well.\nPASS")
    assert v == "pass"
    assert "agent answered well" in r


def test_judge_parse_pure_fail():
    v, r = LLMJudge._parse("agent was wrong.\nFAIL")
    assert v == "fail"


def test_judge_parse_verdict_prefix():
    v, _ = LLMJudge._parse("thinking...\nVERDICT: PASS")
    assert v == "pass"


def test_judge_parse_pass_in_text_ignored_when_fail_present():
    """整段文本里出现 'PASS' 字符 + 'FAIL' 字符,以最后行为准。"""
    v, _ = LLMJudge._parse("there is no PASS guarantee.\nFAIL")
    assert v == "fail"


def test_judge_parse_empty_returns_none():
    v, r = LLMJudge._parse("")
    assert v is None
    assert r == ""


def test_judge_parse_multiline_reasoning():
    v, r = LLMJudge._parse("reasoning line 1\nreasoning line 2\nPASS")
    assert v == "pass"
    assert "reasoning line 1" in r
    assert "reasoning line 2" in r


def test_judge_config_defaults():
    cfg = JudgeConfig()
    assert cfg.model == "gpt-4o-mini"
    assert cfg.protocol == "openai"