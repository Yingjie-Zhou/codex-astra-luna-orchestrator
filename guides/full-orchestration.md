# 完整编排：Pro v2.1

Root 在整个线程固定使用 GPT-5.6 Sol High，负责风险分级、架构、协调、集成和验收。
不要中途切换 root 模型或推理强度，以保留 prompt cache 连续性。

角色名称必须精确。每个子任务报告在使用前，必须用捆绑的 Python 3.11+
`pro_guard.py attest` 核对唯一 rollout session 的实际角色、模型和 effort；任何缺失、
歧义或不匹配都阻塞。它只验证本地证据，不提供密码学防篡改保证。

```text
Sol root (high)
├── Luna auditor (max, read-only)       事实挑战、冲突门禁、行为契约
├── Luna explorer (high, read-only)     仓库取证
├── Luna worker (max)                   bounded writer
├── Luna tester (high)                  测试与构建
├── Luna researcher (high, read-only)   权威资料
├── Sol solver (high)                   复杂 writer
├── Astra reviewer (low, read-only)     设计或经济型 diff 审查
└── Astra reviewer_high (high, read-only) R3 独立终审
```

## 实现前事实门禁

R1-R3 先由 auditor 独立检查用户事实与拟议修复，并把关键 claim 分类为
`CONFIRMED`、`PARTIALLY_CONFIRMED`、`CONTRADICTED` 或 `UNKNOWN`。
报告必须包含证据、`CLEAR/BLOCK`、行为契约和残余不确定性。若机制不能实现期望
行为、违反现有不变量，或结果依赖被否定/未解决的关键事实，则标记 `BLOCK`；
root 在用户确认或更强证据出现前不能开始写入。

## 风险路径

- R0：root-only 机械修改与直接验证。
- R1：auditor -> 单一 bounded writer -> tester -> root。
- R2：auditor -> explorer -> 单一 worker/solver -> tester -> reviewer DIFF
  (Astra low) -> root。
- R3：auditor -> explorer -> reviewer DESIGN (Astra low) -> 单一 Sol solver ->
  tester -> reviewer_high (Astra high) -> root 与所需人工门禁。

安全/权限、不可逆操作、公共 API/schema、数据完整性、并发、部署和大影响面应升到
R3。具体任务的安全限制不会自动成为以后任务的默认规则。

## 上下文、Git 与恢复

每个委派写清目标、范围、约束、验收和文件所有权。子代理只返回结论/证据、改动文件、
验证和风险。没有基线失效证据时不重复全仓扫描或全量测试；修复后只复查 delta 与
受影响边界。

任务开始检查 status、branch、HEAD，在 `codex/<task>` 工作。commit 获授权后，
先检查 staged diff，再提交可逆逻辑检查点；排除 secret、本机配置、二进制、日志、
build 目录和验收产物；绝不自动 push，优先 revert。安装器没有任何 Git 副作用。

可恢复状态由 guard 以 lock + revision CAS + atomic replace 写到
`git rev-parse --git-path codex-tasks/<task>/state.json`，不纳入
版本控制。优先完成事件和有界等待；只有长于 15 分钟且平台支持时使用 15 分钟
heartbeat，否则禁止用轮询模拟。deadline 和有限预算必须持久化。恢复时核对仓库
身份、branch、HEAD、status fingerprint；变化令既有验收失效。候选验收绑定文件
digest 和 dirty fingerprint。

报告/摘录/root 摘要上限分别是 8192/20480/12288 UTF-8 字节。不得静默截断；
超限必须阻塞，或换成 guard 校验的路径、SHA-256、字节数引用。

## 验收

自动门禁单独列出测试、lint、build、diff check 的命令和结果。桌面任务需要可运行
候选时，用目标项目命令构建 EXE，报告绝对路径、构建时间、字节大小与 SHA-256，
并将产物排除于 Git。`manual acceptance` 在用户运行前是 `pending`，只有用户
明确确认后才是 `passed`。
