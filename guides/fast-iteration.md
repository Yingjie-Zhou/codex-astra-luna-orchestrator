# 快速迭代

延迟优先时仍使用 `pro`，但减少角色数量：

1. Luna explorer 快速定位路径。
2. Luna worker 完成边界清晰的修改。
3. Luna tester 运行目标测试。
4. Sol root 直接验收。

只在跨文件耦合或非显然调试时加入 Sol。低风险小改动可跳过 reviewer，也不要为了“看起来像多智能体”机械创建所有角色。

短流程不创建 heartbeat；预计超过 15 分钟且当前 Codex surface 支持时才启用。
