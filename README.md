# Codex：Sol + Luna + Astra Pro v2 编排

这套配置用固定的 GPT-5.6 Sol High 根代理保持整条任务的架构判断和
prompt cache 连续性，再按风险选择 Luna、Sol 与 Astra 专职角色。不要在任务中途建议
切换 root 模型或推理强度。

仓库改编自 [codex-astra-luna-orchestrator](https://github.com/donvito/codex-astra-luna-orchestrator)，
只保留 Codex 原生 OpenAI provider 的通用 Pro 流程，不需要额外 API key、本地模型
适配器或模型目录。

## 角色

| 角色 | 模型 / 推理 | 权限 | 职责 |
| --- | --- | --- | --- |
| root | GPT-5.6 Sol / high | 工作区 | 风险分级、架构、拆分、集成和最终验收 |
| auditor | GPT-5.6 Luna / max | 只读 | 实现前核查事实、挑战方案、形成行为契约 |
| explorer | GPT-5.6 Luna / high | 只读 | 搜索和真实代码路径梳理 |
| worker | GPT-5.6 Luna / max | 工作区 | 边界清晰的实现和批量修改 |
| tester | GPT-5.6 Luna / high | 工作区 | 复现、测试、构建和验证 |
| researcher | GPT-5.6 Luna / high | 只读 | 权威资料核对 |
| solver | GPT-5.6 Sol / high | 工作区 | 强耦合实现、跨文件重构和疑难调试 |
| reviewer | GPT-6 Astra / low | 只读 | R2 diff 审查或 R3 实现前设计审查 |
| reviewer_high | GPT-6 Astra / high | 只读 | R3 独立终审 |

auditor 必须把关键事实归为 `CONFIRMED`、`PARTIALLY_CONFIRMED`、
`CONTRADICTED` 或 `UNKNOWN`，并输出可观察行为、不变量、非目标和验收证据。
若用户假设、期望行为和拟议修复之间存在实质语义冲突，流程在实现前阻塞，由 root
用更强证据或用户确认解决。

## R0-R3 风险路由

| 级别 | 路径 | 适用范围 |
| --- | --- | --- |
| R0 | root-only -> 直接验证 | 局部、机械、行为保持的修改 |
| R1 | auditor -> 单一 bounded writer -> tester -> root | 路径清晰、影响受限的行为改动 |
| R2 | auditor -> explorer -> 单一 writer -> tester -> Astra low -> root | 跨文件/组件或有明显回归面 |
| R3 | auditor -> explorer -> Astra low 设计审查 -> Sol solver -> tester -> Astra high 独立终审 -> root/人工门禁 | 安全、权限、不可逆操作、API/schema、数据完整性、并发、部署或大影响面 |

R1 通常由 worker 写入；R2 依耦合度选 worker 或 solver；R3 由 solver 作为唯一
实现者。安全限制来自具体任务，不能把一次任务的特殊限制永久扩张为默认规则。
每个文件或子系统只有一个 writer。

## Profiles

| Profile | 配置差异 | 最大并发子任务 |
| --- | --- | ---: |
| `pro` | 完整 Pro v2 角色 | 4 |
| `pro-max-2-subagents` | 仅降低并发，其他文件和角色完全一致 | 2 |

## 安装

前置条件是 Codex CLI、桌面端或 IDE 扩展、可用的 Astra/Luna/Sol 权限，以及一个
不同于本安装仓库的目标项目。

Windows PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Linux/macOS：

```sh
./setup.sh
```

安装器可安装 `.codex/`、`.agents/` 和 `AGENTS.md`。代理 TOML 通过目录递归
复制，新增角色无需安装器特例。目标 `AGENTS.md` 中由
`<!-- BEGIN CODEX PRO WORKFLOW -->` 与 `<!-- END CODEX PRO WORKFLOW -->`
包围的受管块会被原位替换；块外内容始终保留，重复安装幂等。若发现旧版未加标记的
编排文字，安装器会保留并明确警告，避免静默删除用户规则。

从旧版 DeepSeek 流程升级时，安装器仍只识别并经确认删除 `.codex/` 下六个已知
旧适配器文件；自定义目录和非 DeepSeek 的 `models.json` 不受影响。安装器绝不会
创建 Git 分支或 commit。

## Git 与可恢复状态

任务开始先检查 status、branch 与 HEAD，并使用 `codex/<task>` 分支。用户允许
commit 时，在检查 staged diff 后按可逆的逻辑检查点提交；排除 secret、机器本地
配置、二进制、日志、构建目录和验收产物。绝不自动 push，回退优先新增 revert
commit，而不是重写共享历史。

长任务把状态写入 Git 目录下而非工作树，例如：

```text
git rev-parse --git-path codex-tasks/<task>/state.json
```

状态只需记录风险级别、阶段、branch/HEAD、活跃子任务、文件所有权、已完成检查和
下一步。子代理返回简短结构化报告；无新证据时不重复全仓扫描、全量测试或全 diff
审查，修复后只复查 delta 和受影响边界。优先事件通知和有界等待；只有预计超过
15 分钟且界面支持时才启用 15 分钟 heartbeat，不能用忙轮询代替。

## 自动验收与人工验收

自动测试、lint、构建和 diff check 必须报告精确命令与结果，但不能替代人工验收。
桌面任务若需要用户可运行的候选版本，最终门禁使用目标项目自己的构建命令生成
EXE，并报告绝对路径、构建时间、字节大小和 SHA-256。产物必须排除在 Git 外；
用户尚未实际运行时标记 `manual acceptance: pending`，仅在用户明确确认后标记
`passed`。本通用仓库不硬编码任何具体桌面项目的构建命令。

## 验证

仓库测试需要 Python 3.11+：

```powershell
python -m unittest discover -s tests -v
```

测试覆盖角色配置、两套 profile 一致性、受管块首次安装/升级/幂等、无关内容保留、
旧规则警告、安装器语法、DeepSeek 旧文件边界和 token usage 解析。

## 更多说明

- [完整 R0-R3 编排](guides/full-orchestration.md)
- [快速迭代](guides/fast-iteration.md)
- [复杂仓库任务](guides/complex-repo-work.md)
- [日常编码](guides/routine-coding.md)
- [用量统计](guides/token-usage.md)

## License

Apache-2.0，见 [LICENSE](LICENSE)。
