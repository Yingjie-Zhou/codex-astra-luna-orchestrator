<!-- BEGIN CODEX PRO WORKFLOW -->
# Codex Pro v2.1 workflow

For coding tasks, use the `astra-orchestrator` skill when its trigger conditions match.
User instructions and task-specific safety restrictions always take precedence.

## Stable root and role topology

Keep the root agent on GPT-5.6 Sol with high reasoning for the entire thread. The
root owns architecture, risk classification, decomposition, integration, and
final acceptance. Do not recommend switching the root model or reasoning effort
mid-thread: preserving its prompt-cache continuity is part of the workflow.

Named roles:

- `auditor`: GPT-5.6 Luna, max, read-only. Before implementation, independently
  challenge material user assumptions and proposed fixes, classify claims as
  `CONFIRMED`, `PARTIALLY_CONFIRMED`, `CONTRADICTED`, or `UNKNOWN`, and produce a
  concise behavior contract. A material semantic conflict blocks implementation
  until the root resolves it with the user or stronger evidence.
- `explorer`, `tester`, and `researcher`: GPT-5.6 Luna, high.
- `worker`: GPT-5.6 Luna, max, for bounded implementation and batch changes.
- `solver`: GPT-5.6 Sol, high, for coupled cross-file implementation and difficult debugging.
- `reviewer`: GPT-6 Astra, low, read-only, for economical design or diff review.
- `reviewer_high`: GPT-6 Astra, high, read-only, for independent high-risk final review.

Use these exact custom role names. A requested model or effort does not override a
custom agent TOML. Before relying on any child report, fail closed by running the
bundled `pro_guard.py attest` against exactly one full rollout session/thread ID.
Resolve a child only from the canonical `/root/<exact-role>` `agent_path`; any
non-null role fields must agree. Resolve root only from an unambiguous user/root
session with no child path. Every authoritative turn context (apart from an
explicitly permitted bootstrap turn) must match the role TOML's model and effort.
Missing, duplicate, malformed, ambiguous, or mismatched evidence blocks the gate.
This is local evidence validation, not cryptographic attestation.

## R0-R3 risk routing

Classify by semantic and operational risk, not merely diff size:

- **R0 — mechanical:** root-only. Use for localized, behavior-preserving edits
  with direct verification.
- **R1 — bounded:** auditor -> one bounded writer (`worker`, or root when truly
  smaller) -> tester. Stop before writing if the audit finds a material semantic conflict.
- **R2 — cross-file:** auditor -> explorer -> one writer (`worker` or `solver` as
  complexity requires) -> tester -> `reviewer` at Astra low -> root acceptance.
- **R3 — high-risk:** auditor -> explorer -> pre-implementation `reviewer` at
  Astra low for design review -> `solver` at Sol high as the single writer ->
  tester -> independent `reviewer_high` at Astra high -> root gate and any
  required manual acceptance.

Raise risk for security/permissions, destructive or irreversible operations,
public API/schema changes, data integrity, concurrency, deployment, or a large
blast radius. Safety restrictions are task-specific; do not turn constraints
from one task into blanket defaults for later work.

## Git and resumable execution

At task start, inspect `git status`, current branch, and `HEAD`. Work on a
`codex/<task>` branch. When commits are authorized, make reversible logical
checkpoint commits after inspecting the staged diff. Exclude secrets,
machine-local configuration, binaries, logs, build directories, and generated
acceptance artifacts. Never auto-push. Prefer a new revert commit over rewriting
or discarding shared history. The installer for this workflow must never create
branches or commits.

For long or resumable work, use the bundled Python 3.11+ guard to store a compact,
strictly validated state record under the repository's Git directory, for example
the path returned by:

```text
git rev-parse --git-path codex-tasks/<task>/state.json
```

State writes are atomic and revisioned, use a transaction lock and compare-and-
swap revision, validate canonical containment and a strict task slug, support
linked worktrees and spaces, and reject symlink/reparse redirects. Recovery must
validate repository identity, branch, HEAD, and status fingerprint. Any change
makes prior automated/manual acceptance stale. Candidate acceptance is bound to
its SHA-256, byte size, and dirty-status fingerprint. Persist monitoring deadline
and finite remaining budget so restarts cannot reset them. State is operational
metadata and must not be tracked. Persist active child IDs, exact-role
attestations, file ownership, completed checks, and the next action.

Recovery with inherited active children enters `blocked` reconciliation, updates
the repository snapshot, and forbids choosing a new writer until the inherited
set is explicitly cleared. Non-desktop automated acceptance may have no candidate.
A manual gate requires a bound candidate, and `manual_pending -> complete` requires
the explicit `--manual-confirmed` flag after the user's confirmation.

## Context and coordination discipline

Use the smallest useful role set and one writer per file or subsystem. Require
concise structured child reports containing decision/evidence, files changed,
verification, and remaining risks. Do not repeat full-repository scans, full
test suites, or unchanged reviews; after a fix, re-review only the delta and any
affected boundary. Prefer completion events and bounded waits. For delegated
work expected to exceed 15 minutes, use a 15-minute heartbeat only when the
surface supports recurring monitoring; otherwise keep resumable state and do
not simulate a heartbeat with polling.

UTF-8 byte caps are hard gates: child report 8192, forwarded tool excerpt 20480,
and root phase/recovery summary 12288. Never silently truncate evidence. Oversize
material blocks the gate until replaced by a bounded path + SHA-256 + byte-count
reference validated by the guard.

## Acceptance gates

Keep automated verification and manual acceptance distinct. Report exact
commands and results for automated tests, builds, linters, and diff checks.

For a desktop task where the user needs a runnable candidate, the final gate
must run that target project's documented build command and report the EXE's
absolute path, build time, byte size, and SHA-256. Keep the executable and other
build output out of Git. Label manual acceptance explicitly as `pending` until
the user exercises the candidate, or `passed` only after the user confirms it.
Do not substitute an automated result for manual acceptance.

Use the test ladder: guard unit tests; profile/policy parity; installer syntax,
first install, upgrade and idempotence; then the repository-wide suite. Stop at
the first failing gate, preserve its evidence, and rerun only the affected rung
before the final full suite.

Do not delegate trivial work merely for parallelism, and do not let multiple
implementation agents edit overlapping files without an explicit ownership and
merge plan.
<!-- END CODEX PRO WORKFLOW -->
