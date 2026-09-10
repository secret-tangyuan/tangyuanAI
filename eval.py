"""tangyuanAI eval —— v1.4.0 引入的评测框架。

核心概念:
- EvalCase 单个用例 (prompt + expected_keywords + expected_tool_calls)
- EvalSuite 一组用例 (跑同一个 agent)
- EvalResult 单条 case 的结果 (pass_rate, latency, token_drift, judge_verdict)
- LLMJudge 用便宜模型(haiku / gpt-4o-mini)对输出打分
- ReplayRecorder 把 agent 的真实 LLM 响应落到 JSONL,后续 replay 用于 prompt 改动的 A/B

CLI: tangyuanai eval {run, bench, replay, judge}
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from .judge import LLMJudge

_logger = logging.getLogger(__name__)


@dataclass
class EvalCase:
    """单个评测用例。

    expected_keywords: 期望 LLM 回复里包含的关键词(任一即 pass,空列表跳过 keyword check)
    expected_tool_calls: 期望 LLM 调用的工具名列表(顺序不重要,空列表跳过 tool check)
    judge_criteria: LLM-as-judge 的评分 prompt(如"判断是否礼貌")
    """

    name: str
    prompt: str
    expected_keywords: list = field(default_factory=list)
    expected_tool_calls: list = field(default_factory=list)
    judge_criteria: str = ""


@dataclass
class EvalSuite:
    name: str
    agent_factory: Callable
    cases: list


@dataclass
class EvalResult:
    case_name: str
    prompt: str
    response: str
    pass_rate: float  # 1.0 全过, 0.0 全挂
    keyword_hits: int
    keyword_total: int
    tool_calls_observed: list
    tool_calls_expected: list
    tool_match: float
    avg_latency_ms: float
    token_drift: int = 0  # placeholder;具体 token 比较在 judge 中做
    judge_verdict: Optional[str] = None  # "pass" / "fail" / None
    judge_reasoning: str = ""
    error: Optional[str] = None


def _keyword_match(response: str, keywords: list) -> tuple:
    if not keywords:
        return 0, 0
    hits = sum(1 for kw in keywords if kw in response)
    return hits, len(keywords)


def _tool_match(observed: list, expected: list) -> tuple:
    """返 (pass_rate, observed 列表)。

    不要求顺序,但 observed 应该包含 expected 里所有工具名。
    """
    if not expected:
        return 1.0, observed
    obs_set = {tc.get("name") if isinstance(tc, dict) else tc for tc in observed}
    exp_set = set(expected)
    matched = len(obs_set & exp_set)
    return matched / len(exp_set), observed


def _extract_tool_calls(response_obj: Any) -> list:
    """从 agent.conversation 返回的对象里提 tool_calls。返回 [{name, ...}, ...]"""
    # 占位:未来可从 response_obj 取
    return []


def run_case(
    agent,
    case: EvalCase,
    *,
    judge: Optional["LLMJudge"] = None,
) -> EvalResult:
    """跑单个 case,返回 EvalResult。"""
    started = time.time()
    response = ""
    error = None
    try:
        response = agent.conversation(case.prompt)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    elapsed_ms = (time.time() - started) * 1000

    # tool calls:从 agent.history 最后一条 assistant 提
    tool_calls_observed = []
    try:
        history = getattr(agent, "history", []) or []
        for msg in reversed(history):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                tool_calls_observed = msg.get("tool_calls") or []
                break
    except Exception:
        pass

    kh, kt = _keyword_match(response, case.expected_keywords)
    tm, tool_calls_observed = _tool_match(tool_calls_observed, case.expected_tool_calls)

    # keyword + tool 各占 50%;keyword_hit / keyword_total * 0.5 + tool_match * 0.5
    kw_score = (kh / kt) if kt > 0 else 0.5  # 没设 keywords 时给半权
    pass_rate = round(kw_score * 0.5 + tm * 0.5, 3)

    verdict = None
    reasoning = ""
    if judge is not None and case.judge_criteria:
        try:
            verdict, reasoning = judge.judge(case.prompt, response, case.judge_criteria)
        except Exception as e:
            reasoning = f"judge 失败: {e}"

    return EvalResult(
        case_name=case.name,
        prompt=case.prompt,
        response=response,
        pass_rate=pass_rate,
        keyword_hits=kh,
        keyword_total=kt,
        tool_calls_observed=tool_calls_observed,
        tool_calls_expected=case.expected_tool_calls,
        tool_match=tm,
        avg_latency_ms=elapsed_ms,
        judge_verdict=verdict,
        judge_reasoning=reasoning,
        error=error,
    )


def run_suite(
    suite: EvalSuite,
    *,
    judge: Optional["LLMJudge"] = None,
) -> list:
    """跑整个 suite,返回 EvalResult 列表。"""
    results = []
    for case in suite.cases:
        agent = suite.agent_factory()
        # 重置 history 让每个 case 独立
        if hasattr(agent, "history"):
            try:
                agent.history = []
            except Exception:
                pass
        result = run_case(agent, case, judge=judge)
        results.append(result)
    return results


def render_table(results: list, *, stream=None) -> None:
    """人类可读的 pass/fail 表。stream 默认 sys.stdout。"""
    import sys
    if stream is None:
        stream = sys.stdout
    if not results:
        print("(no results)", file=stream)
        return
    # 头部
    headers = ["case", "pass_rate", "kw", "tool", "latency_ms", "judge"]
    rows = []
    for r in results:
        kw = f"{r.keyword_hits}/{r.keyword_total}" if r.keyword_total else "-"
        tool = f"{r.tool_match:.0%}" if r.tool_calls_expected else "-"
        judge = r.judge_verdict or "-"
        rows.append([r.case_name, f"{r.pass_rate:.0%}", kw, tool, f"{r.avg_latency_ms:.0f}", judge])

    # 计算列宽
    col_widths = [max(len(headers[i]), max((len(row[i]) for row in rows), default=0)) for i in range(len(headers))]
    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)

    print(fmt.format(*headers), file=stream)
    print(fmt.format(*["-" * w for w in col_widths]), file=stream)
    for row in rows:
        print(fmt.format(*row), file=stream)

    # 汇总
    if results:
        avg_pass = sum(r.pass_rate for r in results) / len(results)
        avg_latency = sum(r.avg_latency_ms for r in results) / len(results)
        print(file=stream)
        print(f"summary: {len(results)} cases, avg pass_rate={avg_pass:.1%}, avg latency={avg_latency:.0f}ms", file=stream)


__all__ = [
    "EvalCase",
    "EvalSuite",
    "EvalResult",
    "run_case",
    "run_suite",
    "render_table",
]
