# 复杂仓库任务

Pro v2.1 在使用任何子代理输出前，先对精确角色名和完整 rollout session 运行
`pro_guard.py attest`；角色、模型或 effort 任一不符即停止。R3 状态阶段和验收通过
guard 的 lock、CAS 与恢复校验推进，不凭自然语言摘要跳过门禁。

跨文件或组件任务至少按 R2 处理；涉及安全/权限、不可逆操作、公共 API/schema、
数据完整性、并发、部署或大影响面时按 R3。

## R2

1. Luna Max auditor 核对关键事实和修复方案，输出分类 claim 与行为契约；`BLOCK`
   时停止。
2. Luna High explorer 找到最小真实实现面。
3. Root 选择单一 writer：边界清晰用 Luna Max worker，强耦合用 Sol High solver。
4. Luna High tester 独立验证。
5. Astra Low reviewer 审查真实 diff，root 集成并验收。

## R3

1. auditor 与 explorer 完成事实和代码取证。
2. Astra Low reviewer 在写入前以 DESIGN 模式挑战设计。
3. Sol High solver 作为唯一实现者。
4. Luna High tester 执行目标验证。
5. 未参与实现的 Astra High `reviewer_high` 做独立终审。
6. Root 完成自动门禁；需要用户实际运行或主观确认的部分保持
   `manual acceptance: pending`。

Root 始终固定为 GPT-5.6 Sol High，不在中途切换模型/推理。任务开始检查 Git
status、branch、HEAD，在 `codex/<task>` 分支工作；用户授权 commit 时先检查
staged diff，再做可逆逻辑检查点，绝不自动 push。

状态保存在 Git 目录的 `codex-tasks/<task>/state.json`，不跟踪。每个子任务报告
结论/证据、文件、验证和风险；不重复未失效的全仓扫描、全量测试或完整 review。
桌面候选构建需报告 EXE 绝对路径、构建时间、大小和 SHA-256，产物不入 Git。
状态恢复会核对 repository identity、branch、HEAD、status fingerprint，并把变化前
的验收标记为 stale；候选同时绑定 dirty fingerprint。报告、工具摘录和 root 摘要
的 UTF-8 上限分别为 8192、20480、12288 字节，超限不得静默截断。
