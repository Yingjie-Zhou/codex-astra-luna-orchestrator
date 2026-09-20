# 日常编码

一两个文件的清晰修改通常不需要完整编排。Root 能直接完成时不要委派；需要独立上下文时，优先使用 Luna Max worker，再由 Luna High tester 做目标验证。

只在以下情况使用 Sol：

- 多文件行为强耦合
- 调试需要跨组件追踪
- 公共 API、数据模型或依赖可能变化
- Luna worker 已把问题缩小，但仍被复杂推理阻塞

日常任务通常不需要 heartbeat，也不一定需要 Astra reviewer。
