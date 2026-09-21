# 日常编码

Pro v2.1 只接受精确自定义角色名。使用子代理报告前，以 Python 3.11+ guard 从唯一
完整 rollout session 核验实际角色、模型与 effort；失败即关闭，不能仅相信 spawn
请求参数。子报告最多 8192 UTF-8 字节，超限证据改用 guard 校验的路径+digest 引用。

先按语义和操作风险分级，而不是只看 diff 行数。

- R0：纯机械、局部且行为保持，由固定的 Sol High root 直接修改和验证。
- R1：有界行为改动，先由只读 Luna Max auditor 挑战事实和拟议修复，再交一个
  bounded writer，最后由 Luna High tester 验证。
- 一旦涉及跨文件回归面就升级 R2；安全、不可逆、API/schema、数据完整性、并发、
  部署或大影响面升级 R3。

auditor 使用 `CONFIRMED`、`PARTIALLY_CONFIRMED`、`CONTRADICTED`、
`UNKNOWN`，并产出行为契约。实质语义冲突为 `BLOCK`，解决前不写代码。

Root 在整个线程保持 GPT-5.6 Sol High，避免破坏 cache 连续性。使用一个 writer，
复用已有取证和测试，仅验证受影响边界。Git 默认可逆：在 `codex/<task>` 分支上
工作，commit 须获授权、检查 staged diff 且不含 secret、本机配置、二进制、日志或
build 产物；不自动 push。自动测试通过与人工验收通过分别报告。
