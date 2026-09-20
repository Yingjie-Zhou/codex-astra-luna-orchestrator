# Codex project instructions

For complex coding tasks, use the `astra-orchestrator` skill when its trigger conditions match.

The Sol root agent at high reasoning owns architecture, decomposition, integration, and final verification.
Prefer specialized subagents for bounded exploration, implementation, testing, review, and technical research.

Route routine search, batch edits, narrow implementation, research, and testing to
the named Luna roles: explorer, tester, and researcher at high reasoning, and worker
at max reasoning. Route complex cross-file implementation and difficult debugging to
the Sol `solver` role at high reasoning. Use Astra only for independent final review.

For delegated work expected to run longer than 15 minutes, create a 15-minute
heartbeat when the current Codex surface supports recurring thread monitoring.
Use it only to inspect new results, correct drift, or unblock work, and stop it
when all tasks finish. Otherwise prefer event-driven updates over frequent polling.

When recurring monitoring is unavailable, never replace it with a busy polling
loop. Prefer completion events or bounded waits, and do not repeatedly re-read
thread lists, logs, or the repository unless state changed or a specific
diagnostic requires it. Record active child IDs and the current phase once. If a
later wake-up is required, hand that checkpoint to a supervising Windows Codex
app task instead of making the remote root simulate a heartbeat.

Use the smallest useful agent set, normally one to three roles and fewer for
simple tasks. Parallelize only genuinely independent work, avoid repeating a
full-repository scan unless the baseline has been invalidated, and require
concise subagent summaries instead of raw logs. Keep the Sol root focused on
planning, decisions, integration, and final acceptance.

Do not delegate trivial work merely for parallelism.
Do not let multiple implementation agents edit the same files without explicit ownership boundaries.
User instructions always take precedence over this orchestration policy.
