---
name: astra-orchestrator
description: Orchestrate multi-file, cross-component, ambiguous, or high-risk Codex development with a stable Sol High root, a Luna Max pre-implementation auditor, risk-based R0-R3 routing, specialized Luna/Sol writers and testers, and independent Astra reviews.
---

# Sol + Luna + Astra Orchestrator — Pro v2.2

The user's explicit instructions and task-specific safety restrictions always
take precedence.

## Stable topology

Keep the root on GPT-6 Sol with high reasoning for the entire thread. The root
owns risk classification, architecture, decomposition, integration, and final
acceptance. Never recommend changing the root model or reasoning effort
mid-thread because prompt-cache continuity is part of the workflow.

- auditor: GPT-6 Luna, max, read-only — independent fact/behavior audit
- explorer: GPT-6 Luna, high, read-only — repository evidence and code paths
- worker: GPT-6 Luna, max — bounded implementation and batch changes
- tester: GPT-6 Luna, high — reproduction, tests, builds, and validation
- researcher: GPT-6 Luna, high, read-only — primary-source technical research
- solver: GPT-6 Sol, high — coupled implementation and difficult debugging
- reviewer: GPT-6 Astra, low, read-only — R2 diff or R3 design review
- reviewer_high: GPT-6 Astra, high, read-only — independent R3 final review

Use the named custom roles and their configured models; a requested model/effort
does not override a role's TOML. Do not run rollout identity/model attestation
for every child report or make it a phase or acceptance gate. If actual role or
configuration drift is suspected, `scripts/pro_guard.py attest` remains an
optional local diagnostic, not security authentication.

## Auditor gate

Before implementation on R1-R3, the auditor separates the user's observation,
causal explanation or proposed mechanism, and desired outcome. Check each
material claim against the actual implementation and available reproduction or
tests; look for a counterexample, an alternative cause, and adjacent modes that
already behave correctly. Classify claims as `CONFIRMED`,
`PARTIALLY_CONFIRMED`, `CONTRADICTED`, or `UNKNOWN`, then return:

1. a concise claim ledger with evidence;
2. `CLEAR` or `BLOCK` for the conflict gate;
3. a behavior contract covering expected and unchanged behavior, relevant
   mode/state variants, user-visible feedback, non-goals, and concrete acceptance
   examples; and
4. residual uncertainty.

A semantic conflict is material when the requested mechanism would not produce
the desired behavior, would change an already-correct adjacent behavior, or
relies on a contradicted/unresolved fact that can change the outcome. A `BLOCK`
stops implementation until the root resolves it with the user or stronger
evidence. Non-material unknowns do not block. The root checks the contract
against the user's intent before assigning a writer.

## R0-R3 routing

Classify risk by semantics, reversibility, blast radius, and evidence—not only
diff size.

| Risk | Route | Typical scope |
| --- | --- | --- |
| R0 mechanical | root only, then direct verification | localized behavior-preserving change |
| R1 bounded | auditor -> one bounded writer -> tester -> root | contained behavior change with a clear path |
| R2 cross-file | auditor -> explorer -> one writer -> tester -> reviewer (Astra low) -> root | multi-file/component change or meaningful regression surface |
| R3 high-risk | auditor -> explorer -> reviewer DESIGN (Astra low) -> solver -> tester -> reviewer_high (Astra high) -> root/manual gate | security, destructive/irreversible, public API/schema, data integrity, concurrency, deployment, or broad blast radius |

For R1, the writer is normally `worker`, though the root may write a truly
small bounded change. For R2, choose `worker` or `solver` based on coupling.
For R3, the Sol `solver` is the single implementation owner. The low reviewer
must finish the design review before R3 implementation, and the high reviewer
must be independent of implementation.

## Delegation contract

Every delegated task includes the objective, exact scope, relevant context,
constraints, deliverable, acceptance criteria, risk level, and file ownership.
Use one writer per file or subsystem. Read-only roles do not edit. Escalate
architectural, security-sensitive, dependency, schema/API, or scope-expanding
decisions to the root.

Require concise structured reports:

1. decision or evidence;
2. files changed (if authorized);
3. exact validation and result; and
4. remaining risks or required decisions.

Enforce UTF-8 byte caps before forwarding or recording evidence:

- child report: 8192 bytes
- forwarded tool excerpt: 20480 bytes
- root phase or recovery summary: 12288 bytes

Never silently truncate. Oversize material blocks the gate unless replaced with
a bounded reference containing a canonical repository-contained path, SHA-256,
and byte count that the guard verifies.

## Git and checkpoints

At task start inspect status, branch, and HEAD. Work on `codex/<task>`. When
the user has authorized commits, create reversible logical checkpoint commits
only after inspecting the staged diff. Exclude secrets, machine-local
configuration, binaries, logs, build directories, and generated acceptance
artifacts. Never auto-push. Prefer reverting with a new commit over rewriting or
discarding shared history.

The workflow installer must never create a branch or commit.

For resumable work, use Python 3.11+ and the bundled standard-library-only guard
with `policy.json`. Store state in the repository Git directory rather than a
tracked file:

```text
git rev-parse --git-path codex-tasks/<task>/state.json
```

Use the strict phases `draft`, `audited`, `designed`, `implementing`, `testing`,
`reviewing`, `automated_passed`, `manual_pending`, `complete`, and `blocked`.
Every mutation uses the transaction lock, atomic replacement, and expected
revision CAS. Task slugs and canonical containment are validated; linked
worktrees and paths with spaces are supported; symlink/reparse redirects fail.
Existing v2.1 state records remain readable and upgrade to v2.2 on the next
successful CAS write. Reject unknown future state versions without writing.
Recovery validates repository identity, branch, HEAD, and status fingerprint.
Changed evidence makes previous acceptance stale. Candidate acceptance binds
path, byte size, SHA-256, and dirty fingerprint. Monitoring stores both an
absolute deadline and finite remaining budget so restart cannot reset either.
Inherited active children force recovery into blocked reconciliation and prevent
a new writer until explicitly cleared, while the refreshed repository snapshot
allows that reconciliation update to proceed.

## Context and monitoring discipline

Use the smallest useful role set. Do not repeat full-repository scans or full
test suites without evidence that invalidates the earlier baseline. After a
fix, re-review only the delta and affected boundary. Preserve the root's context
for decisions and integration rather than raw logs.

Prefer completion events and bounded waits. Use a 15-minute heartbeat only for
delegated work expected to exceed 15 minutes and only when recurring monitoring
is supported. It should inspect new results, correct drift, unblock work, remain
quiet when unchanged, and stop when all tasks finish. Otherwise rely on the
resumable state record; never simulate a heartbeat with frequent polling.

## Verification and acceptance

Automated verification and manual acceptance are separate gates. Report exact
test, build, lint, and diff-check commands and results. A passing automated gate
does not imply manual acceptance.

For a desktop task where the user needs a runnable candidate, the final gate
runs the target project's documented build command. Report the EXE's absolute
path, build time, byte size, and SHA-256, and keep the artifact/build output out
of Git. Mark manual acceptance `pending` until the user exercises it or
`passed` only after explicit confirmation. Do not hardcode a project-specific
build command into this generic workflow.

Before reporting completion, confirm that required roles finished or explicitly
failed, material findings were resolved, automated gates passed, and manual
acceptance is labeled accurately.

Non-desktop tasks may pass automated and complete with no candidate. A manual
gate requires a bound candidate; moving `manual_pending` to `complete` requires
`--manual-confirmed` and only follows explicit user confirmation.

## Guard and test ladder

The guard commands are `state-init`, `state-update`, `state-transition`,
`state-recover`, `monitor-tick`, and `evidence-check`; `attest` and
`state-record-role` are optional drift diagnostics, never routine gates. Use
`--help` for exact arguments. Run guard unit tests first, profile/policy parity
second, installer syntax/install/upgrade/idempotence third, then the complete
repository suite. Preserve failing evidence and rerun the affected rung before
the final suite.
