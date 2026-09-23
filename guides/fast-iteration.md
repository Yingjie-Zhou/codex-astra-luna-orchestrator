# 快速迭代

快速路径不做例行角色 rollout attestation；怀疑配置漂移时才按需诊断。仍不能
静默截断证据来满足上限。子报告/工具摘录/root 摘要分别限制为
8192/20480/12288 UTF-8 字节。

延迟优先不等于跳过风险判断。Root 在整个线程固定使用 GPT-6 Sol High：

- R0 机械修改由 root 直接完成并验证。
- R1 先用 Luna Max auditor 区分观察、解释和期望，检查反例与相邻模式，形成
  `CLEAR` 的行为契约，再由一个 bounded writer 修改、Luna High tester 验证。
- 发现跨文件影响时升级为 R2，加入 explorer 和 Astra Low diff reviewer。
- 遇到安全、不可逆、API/schema、数据完整性、并发或部署风险时升级为 R3，不再走
  快速路径。

只让一个 writer 拥有文件，子代理使用结论/证据/文件/验证/风险格式返回短报告。
复用已完成的扫描与测试基线，修复后只跑受影响验证并复查 delta。

短流程不创建 heartbeat。长流程优先完成事件；只有预计超过 15 分钟且平台原生支持
时才启用 15 分钟 heartbeat。Git 使用 `codex/<task>` 分支和获授权的可逆检查点，
不自动 push。自动验收与用户人工验收必须分别报告。
