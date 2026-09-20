# Token Usage

这套流程没有固定 token 数。用量取决于仓库大小、任务形状、子任务数量、推理强度和缓存命中率。

## Codex 记录位置

Codex 为每个线程写入 rollout JSONL。关键字段包括：

- `session_meta`：线程、父线程、工作目录和角色
- `turn_context`：本轮模型和推理强度
- `token_usage_record`：输入、缓存输入、输出和推理 token
- `token_count`：累计值及账户时间窗口用量

根线程和子线程按 `session_id` 聚合后，才是一次编排任务的完整成本。

## 统计脚本

`scripts/token_usage.py` 只读扫描本地 session：

```bash
scripts/token_usage.py --list --date 2026-09-07
scripts/token_usage.py --root 01a079f2 --date 2026-09-07
scripts/token_usage.py --latest --date 2026-09-07
scripts/token_usage.py --root 01a079f2 --format json
```

## 可比基准

1. 选择三到四个代表任务：单文件修复、多文件功能、跨组件缺陷和研究任务。
2. 对比 root-only 与 Pro 编排流程。
3. 每次记录各模型的非缓存输入、缓存输入、输出、推理 token、子任务数、墙钟时间及账户窗口变化。
4. 每个单元重复两三次，避免单次排队或缓存波动误导结论。
5. 固定配置：整条线程保持 Sol root high；Luna auditor/worker max，Luna
   explorer/tester/researcher high，Sol solver high，Astra reviewer low，
   reviewer_high high。按 R0-R3 使用角色，不把所有角色机械加入每个任务。

建议结果表：

| Task | Config | Astra uncached/cached/out | Luna uncached/cached/out | Sol uncached/cached/out | Subagents | Wall | 5h delta | 7d delta |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |

## 降低用量

- R0 小任务不启用编排；R1-R3 保留 auditor 的事实和行为门禁。
- 日常搜索、编辑和测试交给 Luna，Sol solver 只处理真正复杂的实现；root
  始终保持 Sol High，避免中途切换破坏 cache 连续性。
- 控制并发；每个子任务都会读取自己的上下文。
- 要求子任务返回短报告，不要把大段日志重新塞回 root。
- R1 可以跳过 Astra；R2 使用 Astra Low，只有 R3 使用实现前 Astra Low 和独立
  Astra High 终审。
- 不要高频轮询长任务；需要时使用 15 分钟 heartbeat。
