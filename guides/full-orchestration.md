# 完整编排：Sol + Luna + Astra

推荐使用 `pro` profile：

```text
Sol root (high)
├── Luna explorer (high)   搜索、仓库路径梳理
├── Luna worker (max)      明确的小功能、批量修改
├── Luna tester (high)     复现、测试、构建
├── Luna researcher (high) 权威资料核对
├── Sol solver (high)      复杂实现、跨文件调试
└── Astra reviewer (low)   独立终审
```

## 工作流

1. Root 明确完成标准、依赖、风险和任务边界。
2. 独立的探索、研究和验证任务可以并行派发。
3. Luna worker 只接边界清晰的实现；复杂或强耦合工作交给 Sol。
4. Root 汇总结果、解决冲突，并保证实现代理的文件所有权不重叠。
5. Luna tester 运行最高价值验证；Astra reviewer 检查真实 diff。
6. 具体问题返回合适角色修复，最后由 root 验收。

## 15 分钟 heartbeat

只为预计明显超过 15 分钟的委派流程创建 heartbeat。每次检查：

- 查看活跃任务和新结果
- 对照验收标准识别漂移
- 缩小、补充上下文、改派或升级阻塞任务
- 跳过已完成任务
- 没有需要干预时保持安静
- 全部完成后删除 heartbeat

没有定时监控能力时使用事件驱动更新和有界等待，不要高频轮询。
