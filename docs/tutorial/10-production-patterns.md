# 10 Production Patterns

> 🎯 学完能让 agent 进生产(production-grade reliability / observability / eval)。

## 概念

v1.4.0 起,tangyuanAI 默认开启 5 类生产级能力:

| 能力 | 默认值 | 关闭方法 |
| --- | --- | --- |
| **tool 结果校验** | pydantic schema,失败进 history 为 `{"ok": false, "error": ...}` | `output_schema=None` |
| **tool 重试** | transient 异常(超时 / 连接 / 5xx)默认 2 次 | `retry=RetryPolicy(max=0)` |
| **tool idempotency** | 1h LRU cache + 自动 hash key | `idempotency_ttl=0` |
| **tracing** | 每个 LLM/tool call 落 `logs/spans.jsonl` | `tangyuanai configure --tracing false` |
| **mid-flight checkpoint** | 每 FC 轮 round 自动 `.tangyuan_checkpoints/` | `auto_checkpoint="never"` |

`protocol_chain`(多 provider fallback)和 `response_cache`(同 prompt 不重复打)是 opt-in,需要在 `config.py` 的 `features` 里显式启用。

`eval` 子命令和 `sandbox` hook 也是 opt-in。

## 5 行代码起步(关掉你不想要的)

```python
@tangyuanAI.tool_registry.register_tool(
    description="发邮件给用户",
    parameters={...},
    idempotency_ttl=0,         # ← 发邮件不能命中 cache,关掉
    retry=None,                # ← 重试可能重复发,关掉
)
def send_email(to: str, body: str): ...
```

## 启用 protocol_chain(多 provider fallback)

`tangyuanai_config.json`:
```json
{
  "features": [{
    "name": "fallback", "type": "protocol_chain", "enabled": true,
    "config": {
      "providers": [
        {"protocol": "openai", "api_provider": "https://api.openai.com/v1", "api_key_env": "API_KEY"},
        {"protocol": "anthropic", "api_provider": "https://api.anthropic.com", "api_key_env": "ANTHROPIC_API_KEY"}
      ],
      "policy": "fallback"
    }
  }]
}
```

## 跑 eval(验证 prompt 改动是否变好)

```bash
# 写 suite
cat > eval_smoke.py <<'EOF'
import tangyuanAI
from tangyuanAI.eval import EvalSuite, EvalCase

suite = EvalSuite(name="basic", agent_factory=lambda: tangyuanAI.agent_list["weather"], cases=[
    EvalCase(name="greet", prompt="打招呼", expected_keywords=["你好"]),
    EvalCase(name="weather", prompt="北京天气", expected_keywords=["北京", "天气"]),
])
EOF

# 跑
tangyuanai eval run --suite eval_smoke.py --agent weather
```

## Sandbox hook(预留)

```python
class MySandbox(tangyuanAI.Sandbox):
    def before(self, func, args):
        # 拦截工具执行,可做路径白名单 / 资源限制
        return True
    def after(self, func, args, result):
        return result

agent = tangyuanAI.agent_list["writer"]
agent.register_sandbox(MySandbox())
```

**实际 sandboxer 实现**(subprocess / docker / wasm)会在后续 PR 加上。

## 完整 demo

- [`MIGRATION.md`](../../MIGRATION.md) —— v1.4.0 升级时的所有 breaking changes
- 各 D 文档:[`docs/tracing.md`](../tracing.md) / [`docs/checkpoint.md`](../checkpoint.md) / [`docs/protocol-chain.md`](../protocol-chain.md) / [`docs/eval.md`](../eval.md)(D1-D5 合入后会建)

## 进阶

- [`CHANGELOG.md`](../../CHANGELOG.md) —— 查每个能力的版本引入时间
- [`MIGRATION.md`](../../MIGRATION.md) —— v1.3.0 / v1.4.0 迁移指南

## 常见问题

**Q: 我升级到 v1.4.0 后行为变了(默认开 trace / checkpoint),怎么排查?**
A: `tangyuanai configure --tracing false --auto-checkpoint never` 全关回 v1.3.0 行为,逐步开。详见 [MIGRATION.md](../../MIGRATION.md)。

**Q: `sandbox` hook 真的安全吗?**
A: `agent._sandbox` 字段只能通过 `agent.register_sandbox(...)` 显式设置,默认是 `NullSandbox`(no-op)。实际 sandboxer 实现需要先经 ACL(`tool_registry.check_permission`),不会绕过工具权限。详细审查在 PR-8 合并时跑过 `security-review` skill。

**Q: response_cache 命中条件是什么?**
A: 默认 `temperature == 0` 且 `tools` 为空。要给高 temperature 或带 tools 的 prompt 缓存,显式 `cache_writes=True`。