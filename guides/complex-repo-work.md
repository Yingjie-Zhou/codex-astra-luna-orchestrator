# 复杂仓库任务

大型仓库继续使用 `pro`。Sol root 使用 high；Luna explorer、tester 和 researcher 使用 high，worker 使用 max；Sol solver 负责跨模块核心实现。

推荐顺序：

1. 多路 Luna explorer/researcher 并行取证。
2. Sol root 汇总证据并决定架构。
3. Luna worker 处理边界清晰且文件不重叠的改动。
4. Sol solver 处理强耦合、跨组件或疑难调试。
5. Luna tester 验证。
6. Astra reviewer 对高风险变更做独立终审。

只为真正独立的工作流增加并发。更多子任务会重复读取上下文，不会自动更快。多个实现代理不得编辑同一文件，除非 root 明确安排所有权和合并策略。
