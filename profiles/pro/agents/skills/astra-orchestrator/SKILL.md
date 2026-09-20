---
name: astra-orchestrator
description: Orchestrate complex Codex work with Sol High as planner and integrator, Luna High for routine exploration, testing, and research, Luna Max for bounded implementation, Sol for difficult implementation, and Astra for independent review. Use for multi-file work, cross-component debugging, parallel workstreams, or explicit delegation requests.
---

# Sol + Luna + Astra Orchestrator — Pro

The user's explicit instructions always take precedence.

## Topology

- root: GPT-5.6 Sol, high — architecture, decomposition, coordination, integration, final acceptance
- explorer: GPT-5.6 Luna, high — repository mapping and evidence gathering
- worker: GPT-5.6 Luna, max — bounded routine implementation and batch changes
- tester: GPT-5.6 Luna, high — reproduction, tests, builds, and validation
- researcher: GPT-5.6 Luna, high — primary-source technical research
- solver: GPT-5.6 Sol, high — difficult implementation, cross-file refactors, and non-obvious debugging
- reviewer: GPT-6 Astra, low — independent final review

Use Luna High for routine exploration, testing, and research, and Luna Max for
bounded implementation. Use the Sol solver when work is too coupled, ambiguous,
or reasoning-heavy for a bounded Luna worker.

## Delegation gate

Classify the task before substantive repository work:

- **root-only**: genuinely small, localized, and not improved by independent
  exploration, implementation, testing, research, or review.
- **delegated**: spans files or components, needs exploration, has independent
  workstreams, benefits from separate implementation and verification context,
  requires current external facts, or was explicitly requested as multi-agent.

When delegated, spawn at least one real subagent before doing the delegated work.
If spawning is unavailable, report that fact instead of pretending delegation
occurred. Do not create subagents solely to satisfy this rule for trivial work.

## Routing

| Work | Role |
| --- | --- |
| Search, inventory, trace code or data flow | explorer |
| Small feature, mechanical edit, formatting, narrow refactor | worker |
| Reproduce, test, lint, build, regression check | tester |
| Current API or framework facts from primary sources | researcher |
| Complex feature, cross-file change, difficult debugging | solver |
| Independent correctness, security, and regression review | reviewer |

The root owns architectural decisions. Subagents return evidence and bounded
results; they do not silently broaden scope or redesign the system.

## Delegation contract

Every task sent to a subagent must include:

- objective: one concrete outcome
- scope: exact files, subsystem, or question
- context: only what is needed to succeed
- constraints: what must not change
- deliverable: findings or edits expected
- acceptance criteria: how the result will be checked

For implementation, assign one writer per file or subsystem. Exploration,
research, and review tasks are read-only unless explicitly authorized.

## Default workflow

1. Analyze the request and state completion criteria, dependencies, and risks.
2. Split independent work into bounded tasks and spawn independent roles before
   waiting for any one of them.
3. Use Luna High for routine exploration, testing, and research, Luna Max for
   bounded implementation, and Sol for genuinely difficult implementation.
4. Wait for required results. Do not make the root perform mechanical work that
   was deliberately delegated.
5. Integrate results, resolve conflicts, and run the highest-value verification.
6. Use the reviewer when an independent final pass is materially useful.
7. Send concrete fixes back to worker, solver, or tester.
8. Report completion only when the acceptance criteria are met.

## Parallelism and ownership

- Parallelize independent exploration, research, and validation.
- Serialize dependent phases: explore -> decide -> implement -> test -> review.
- Never give two implementation agents overlapping file ownership without an
  explicit merge plan.
- Keep reports concise so the root receives decisions, evidence, paths, test
  results, and risks rather than large raw logs.

## Escalation

A Luna role should stop and report when it encounters an architectural decision,
breaking API or schema change, new dependency, security-sensitive choice, or
unexpected work outside its scope.

Escalate routine work to the Sol solver when implementation is cross-cutting or
remains blocked after the task has been narrowed. Keep Astra focused on an
independent final review; the Sol root owns planning, coordination, critical
judgment, and final acceptance.

## Failure handling

When a subagent fails, inspect the reason and then retry, narrow, reassign, or
handle the remaining work in the root with an explicit note. Do not silently
ignore failed delegation or claim it completed.

## Fifteen-minute heartbeat

Use a heartbeat only when delegated work is expected to run long enough that a
15-minute check is useful. Each heartbeat should inspect new results, compare
them with the acceptance criteria, correct drift or unblock work, skip completed
tasks, stay quiet when no action is needed, and stop when all tasks finish.

If recurring monitoring is unavailable, use event-driven updates and bounded
waits. Never simulate a heartbeat with frequent polling.

In that fallback mode:

- wait for collaboration completion events or use a bounded wait;
- read task state, logs, or repository state only after a state change, failure,
  or specific diagnostic need, never on a fixed short interval;
- record active child IDs and the current workflow phase once; and
- when a later wake-up is required, hand that checkpoint to a supervising
  Windows Codex app task. A remote root must not manufacture a polling-based
  heartbeat.

## Cost and context discipline

Use the smallest agent set that can safely complete the work. One to three
delegated roles is the normal range, and simple work should use fewer. Do not
instantiate every available role mechanically.

Parallelize only genuinely independent tasks. Do not repeat a full-repository
scan unless new evidence invalidates the baseline. Require concise reports with
changed files, key findings, verification results, and blockers instead of raw
logs. Keep the Sol root's active work focused on planning, decisions,
integration, and final acceptance.

## Final verification

The root must inspect the final diff and verify the requested behavior. Prefer:

- syntax, type, and configuration parsing checks
- targeted unit and integration tests
- reproduction of the original problem
- an independent reviewer for high-risk changes

Before the final response, confirm every required subagent completed or
explicitly failed, material findings were integrated, conflicts were resolved,
and no required agent is still running.
