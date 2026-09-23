from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "profiles" / "pro" / "agents" / "skills" / "astra-orchestrator"
LIMITED_SKILL = ROOT / "profiles" / "pro-max-2-subagents" / "agents" / "skills" / "astra-orchestrator"
PROFILE_ROOT = ROOT / "profiles" / "pro"
SPEC = importlib.util.spec_from_file_location("pro_guard", SKILL / "scripts" / "pro_guard.py")
assert SPEC and SPEC.loader
guard = importlib.util.module_from_spec(SPEC)
sys.dont_write_bytecode = True
SPEC.loader.exec_module(guard)


def write_rollout(path: Path, session: str, role: str, model: str, effort: str) -> None:
    if role == "root":
        session_payload = {
            "id": session,
            "session_id": session,
            "thread_source": "user",
            "cwd": str(path.parent),
            "git": {},
            "cli_version": "test",
        }
    else:
        parent = "parent-root-session"
        session_payload = {
            "id": session,
            "session_id": parent,
            "parent_thread_id": parent,
            "agent_path": f"/root/{role}",
            "agent_role": None,
            "agent_nickname": "fixture-nickname",
            "source": {"subagent": {"thread_spawn": {"agent_role": None}}},
            "cwd": str(path.parent),
            "git": {},
            "cli_version": "test",
        }
    records = [
        {
            "type": "session_meta",
            "timestamp": "2026-01-01T00:00:00Z",
            "payload": session_payload,
        },
        {
            "type": "turn_context",
            "timestamp": "2026-01-01T00:00:01Z",
            "payload": {
                "turn_id": "turn-1",
                "model": model,
                "effort": effort,
                "cwd": str(path.parent),
                "workspace_roots": [str(path.parent)],
                "approval_policy": "never",
                "sandbox_policy": "read-only",
            },
        },
    ]
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def git(repo: Path, *args: str) -> None:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)


class ProGuardTests(unittest.TestCase):
    def test_profile_guard_and_policy_are_identical(self) -> None:
        for relative in (Path("policy.json"), Path("scripts/pro_guard.py")):
            with self.subTest(relative=relative):
                self.assertEqual((SKILL / relative).read_bytes(), (LIMITED_SKILL / relative).read_bytes())

    def test_policy_is_strict_and_has_exact_caps(self) -> None:
        policy = guard.load_policy()
        self.assertEqual(policy["workflow_version"], "2.2")
        self.assertEqual(
            policy["evidence_caps_utf8_bytes"],
            {"child_report": 8192, "forwarded_tool_excerpt": 20480, "root_phase_or_recovery_summary": 12288},
        )
        altered = json.loads((SKILL / "policy.json").read_text(encoding="utf-8"))
        altered["unexpected"] = True
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaises(guard.GuardError):
                guard.load_policy(path)

    def test_rollout_attestation_accepts_exact_role_and_rejects_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "rollout.jsonl"
            write_rollout(rollout, "session-ok", "reviewer_high", "gpt-6-astra", "high")
            result = guard.attest_rollout(rollout, "session-ok", "reviewer_high", profile_root=PROFILE_ROOT)
            self.assertTrue(result["attested"])
            self.assertEqual(result["resolved_role"], "reviewer_high")
            with self.assertRaises(guard.GuardError):
                guard.attest_rollout(rollout, "session-ok", "reviewer", profile_root=PROFILE_ROOT)

    def test_actual_root_and_subagent_shapes_fail_closed_on_conflicting_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            root_rollout = directory / "root.jsonl"
            write_rollout(root_rollout, "root-actual", "root", "gpt-6-sol", "high")
            root = guard.attest_rollout(root_rollout, "root-actual", "root", profile_root=PROFILE_ROOT)
            self.assertEqual(root["resolved_role"], "root")

            child_rollout = directory / "child.jsonl"
            write_rollout(child_rollout, "child-actual", "tester", "gpt-6-luna", "high")
            child = guard.attest_rollout(child_rollout, "child-actual", "tester", profile_root=PROFILE_ROOT)
            self.assertEqual(child["resolved_role"], "tester")
            with self.assertRaises(guard.GuardError):
                guard.attest_rollout(child_rollout, "parent-root-session", "tester", profile_root=PROFILE_ROOT)
            records = [json.loads(line) for line in child_rollout.read_text(encoding="utf-8").splitlines()]
            records[0]["payload"]["source"]["subagent"]["thread_spawn"]["agent_role"] = "reviewer"
            child_rollout.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            with self.assertRaises(guard.GuardError):
                guard.attest_rollout(child_rollout, "child-actual", "tester", profile_root=PROFILE_ROOT)

            write_rollout(child_rollout, "child-actual", "tester", "gpt-6-luna", "high")
            records = [json.loads(line) for line in child_rollout.read_text(encoding="utf-8").splitlines()]
            records[0]["payload"]["parent_thread_id"] = "different-parent"
            child_rollout.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            with self.assertRaises(guard.GuardError):
                guard.attest_rollout(child_rollout, "child-actual", "tester", profile_root=PROFILE_ROOT)

            records[0]["payload"].pop("id")
            records[0]["payload"]["parent_thread_id"] = records[0]["payload"]["session_id"]
            child_rollout.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            with self.assertRaises(guard.GuardError):
                guard.attest_rollout(child_rollout, "child-actual", "tester", profile_root=PROFILE_ROOT)

    def test_rollout_attestation_rejects_duplicate_malformed_and_inconsistent_turns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            first = directory / "one.jsonl"
            second = directory / "two.jsonl"
            write_rollout(first, "duplicate", "auditor", "gpt-6-luna", "max")
            write_rollout(second, "duplicate", "auditor", "gpt-6-luna", "max")
            with self.assertRaises(guard.GuardError):
                guard.attest_rollout(directory, "duplicate", "auditor", profile_root=PROFILE_ROOT)
            second.unlink()
            with first.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"type": "turn_context", "payload": {"turn_id": "bad", "model": "gpt-6-astra", "effort": "high"}}) + "\n")
            with self.assertRaises(guard.GuardError):
                guard.attest_rollout(first, "duplicate", "auditor", profile_root=PROFILE_ROOT)
            first.write_text("not-json\n", encoding="utf-8")
            with self.assertRaises(guard.GuardError):
                guard.attest_rollout(first, "duplicate", "auditor", profile_root=PROFILE_ROOT)

    def test_evidence_caps_block_inline_and_verify_reference(self) -> None:
        policy = guard.load_policy()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            self.assertEqual(guard.validate_evidence("x" * 8192, "child_report", repo, policy), "x" * 8192)
            with self.assertRaises(guard.GuardError):
                guard.validate_evidence("é" * 4097, "child_report", repo, policy)
            evidence = repo / "evidence.txt"
            evidence.write_bytes(b"z" * 9000)
            reference = {"path": "evidence.txt", "bytes": 9000, "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
            self.assertEqual(guard.validate_evidence(reference, "child_report", repo, policy), reference)
            reference["sha256"] = "0" * 64
            with self.assertRaises(guard.GuardError):
                guard.validate_evidence(reference, "child_report", repo, policy)

    def test_dirty_fingerprint_changes_for_already_dirty_and_untracked_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pro guard fingerprint ") as tmp:
            repo = Path(tmp)
            git(repo, "init")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "Pro Guard Test")
            tracked = repo / "tracked.txt"
            tracked.write_text("clean", encoding="utf-8")
            git(repo, "add", "tracked.txt")
            git(repo, "commit", "-m", "fixture")
            tracked.write_text("dirty-one", encoding="utf-8")
            first = guard.repository_snapshot(repo)["status_sha256"]
            tracked.write_text("dirty-two", encoding="utf-8")
            second = guard.repository_snapshot(repo)["status_sha256"]
            self.assertNotEqual(first, second)

            untracked = repo / "untracked.txt"
            untracked.write_text("untracked-one", encoding="utf-8")
            third = guard.repository_snapshot(repo)["status_sha256"]
            untracked.write_text("untracked-two", encoding="utf-8")
            fourth = guard.repository_snapshot(repo)["status_sha256"]
            self.assertNotEqual(third, fourth)

    def test_streamed_process_stderr_cannot_deadlock_and_diagnostics_are_bounded(self) -> None:
        noisy_success = [
            sys.executable,
            "-c",
            "import os; os.write(2, b'e' * 262144); os.write(1, b'a\\0b\\0')",
        ]
        output = b"".join(guard._iter_process_stdout(noisy_success, "noisy success"))
        self.assertEqual(output, b"a\0b\0")

        noisy_failure = [
            sys.executable,
            "-c",
            "import os,sys; os.write(2, b'f' * 262144); sys.exit(7)",
        ]
        with self.assertRaises(guard.GuardError) as captured:
            list(guard._iter_process_stdout(noisy_failure, "noisy failure"))
        message = str(captured.exception)
        self.assertIn("failed (7)", message)
        self.assertIn("stderr truncated at 20480 bytes", message)
        self.assertLess(len(message.encode("utf-8")), 22000)

    def test_installed_profile_root_cli_and_ambiguous_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "installed"
            agents = root / ".codex" / "agents"
            agents.mkdir(parents=True)
            shutil.copy2(PROFILE_ROOT / "codex" / "agents" / "reviewer_high.toml", agents / "reviewer_high.toml")
            rollout = Path(tmp) / "installed-rollout.jsonl"
            write_rollout(rollout, "installed-child", "reviewer_high", "gpt-6-astra", "high")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SKILL / "scripts" / "pro_guard.py"),
                    "attest",
                    "--rollout",
                    str(rollout),
                    "--session",
                    "installed-child",
                    "--role",
                    "reviewer_high",
                    "--profile-root",
                    str(root),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["attested"])
            (root / "codex").mkdir()
            with self.assertRaises(guard.GuardError):
                guard.attest_rollout(rollout, "installed-child", "reviewer_high", profile_root=root)

    def test_r3_state_progresses_without_role_attestation_but_waits_for_children(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pro guard no attestation ") as tmp:
            repo = Path(tmp)
            git(repo, "init")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "Pro Guard Test")
            (repo / "tracked.txt").write_text("fixture", encoding="utf-8")
            git(repo, "add", "tracked.txt")
            git(repo, "commit", "-m", "fixture")
            _, state = guard.init_state(repo, "optional-identity", "R3")
            for phase in ("audited", "designed", "implementing", "testing", "reviewing"):
                state = guard.transition_state(repo, "optional-identity", state["revision"], phase)
            self.assertEqual(state["roles"], {})
            state = guard.update_state(
                repo, "optional-identity", state["revision"],
                active_children={"still-running": "tester"},
            )
            with self.assertRaisesRegex(guard.GuardError, "active child"):
                guard.transition_state(repo, "optional-identity", state["revision"], "automated_passed")
            state = guard.update_state(repo, "optional-identity", state["revision"], active_children={})
            state = guard.transition_state(repo, "optional-identity", state["revision"], "automated_passed")
            state = guard.transition_state(repo, "optional-identity", state["revision"], "complete")
            self.assertEqual(state["roles"], {})

    def test_v21_state_is_readable_and_upgrades_only_after_successful_cas(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pro guard v21 migration ") as tmp:
            repo = Path(tmp)
            git(repo, "init")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "Pro Guard Test")
            (repo / "tracked.txt").write_text("fixture", encoding="utf-8")
            git(repo, "add", "tracked.txt")
            git(repo, "commit", "-m", "fixture")
            path, state = guard.init_state(repo, "v21-cas", "R0")
            self.assertEqual(state["workflow_version"], "2.2")
            legacy = {**state, "workflow_version": "2.1"}
            path.write_text(json.dumps(legacy), encoding="utf-8")
            original_bytes = path.read_bytes()

            self.assertEqual(guard.read_state(path, guard.load_policy()), legacy)
            with self.assertRaisesRegex(guard.GuardError, "revision CAS mismatch"):
                guard.update_state(repo, "v21-cas", state["revision"] + 1, next_action="must not write")
            self.assertEqual(path.read_bytes(), original_bytes)

            upgraded = guard.update_state(repo, "v21-cas", state["revision"], next_action="continue")
            self.assertEqual(upgraded["revision"], 1)
            self.assertEqual(upgraded["workflow_version"], "2.2")
            self.assertEqual(guard.read_state(path, guard.load_policy())["workflow_version"], "2.2")

    def test_v21_recovery_upgrades_and_unknown_future_state_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pro guard v21 recovery ") as tmp:
            repo = Path(tmp)
            git(repo, "init")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "Pro Guard Test")
            tracked = repo / "tracked.txt"
            tracked.write_text("fixture", encoding="utf-8")
            git(repo, "add", "tracked.txt")
            git(repo, "commit", "-m", "fixture")
            path, state = guard.init_state(repo, "v21-recover", "R0")
            legacy = {**state, "workflow_version": "2.1"}
            path.write_text(json.dumps(legacy), encoding="utf-8")
            tracked.write_text("changed", encoding="utf-8")

            recovered = guard.recover_state(repo, "v21-recover", state["revision"])
            self.assertEqual(recovered["workflow_version"], "2.2")
            self.assertEqual(recovered["revision"], 1)
            self.assertEqual(recovered["repository"], guard.repository_snapshot(repo))
            self.assertEqual(guard.read_state(path, guard.load_policy())["workflow_version"], "2.2")

            future = {**recovered, "workflow_version": "2.3"}
            path.write_text(json.dumps(future), encoding="utf-8")
            future_bytes = path.read_bytes()
            with self.assertRaisesRegex(guard.GuardError, "unsupported state version"):
                guard.read_state(path, guard.load_policy())
            with self.assertRaisesRegex(guard.GuardError, "unsupported state version"):
                guard.update_state(repo, "v21-recover", recovered["revision"], next_action="must not write")
            self.assertEqual(path.read_bytes(), future_bytes)

    def test_revisioned_state_candidate_recovery_and_monitor_budget(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pro guard repo ") as tmp:
            repo = Path(tmp) / "repository"
            repo.mkdir()
            git(repo, "init")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "Pro Guard Test")
            candidate = repo / "candidate.bin"
            candidate.write_bytes(b"candidate-v1")
            git(repo, "add", "candidate.bin")
            git(repo, "commit", "-m", "fixture")
            deadline = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z")
            state_file, state = guard.init_state(repo, "state-test", "R0", deadline=deadline, budget=2)
            self.assertIn("codex-tasks", str(state_file))
            with self.assertRaises(guard.GuardError):
                guard.transition_state(repo, "state-test", 99, "implementing")
            state = guard.update_state(
                repo,
                "state-test",
                state["revision"],
                active_children={"full-child-session-id": "tester"},
                ownership={"candidate.bin": "root"},
                check={"name": "baseline", "status": "passed", "evidence": "clean fixture"},
                next_action="complete verification",
            )
            self.assertEqual(state["active_children"]["full-child-session-id"], "tester")
            self.assertEqual(state["checks"][0]["status"], "passed")

            rollout = Path(tmp) / "tester.jsonl"
            write_rollout(rollout, "full-child-session-id", "tester", "gpt-6-luna", "high")
            attestation = guard.attest_rollout(rollout, "full-child-session-id", "tester", profile_root=PROFILE_ROOT)
            attestation_file = Path(tmp) / "attestation.json"
            attestation_file.write_text(json.dumps(attestation), encoding="utf-8")
            state = guard.record_role_state(repo, "state-test", state["revision"], attestation_file)
            self.assertEqual(state["active_children"], {"full-child-session-id": "tester"})
            changed_policy = json.loads(json.dumps(guard.load_policy()))
            changed_policy["roles"]["tester"]["model"] = "replacement-model"
            guard.validate_state(state, changed_policy)
            state = guard.update_state(repo, "state-test", state["revision"], active_children={})
            state = guard.transition_state(repo, "state-test", state["revision"], "implementing")
            state = guard.transition_state(repo, "state-test", state["revision"], "testing")
            state = guard.transition_state(repo, "state-test", state["revision"], "automated_passed", candidate_path=candidate)
            self.assertEqual(state["automated_acceptance"], "passed")
            candidate.write_bytes(b"candidate-v2")
            state = guard.recover_state(repo, "state-test", state["revision"])
            self.assertEqual(state["automated_acceptance"], "stale")
            self.assertEqual(state["phase"], "testing")
            state = guard.monitor_tick(repo, "state-test", state["revision"])
            self.assertEqual(state["monitor"]["remaining_budget"], 1)
            with self.assertRaises(guard.GuardError):
                guard.transition_state(repo, "state-test", state["revision"], "automated_passed", manual_required=True)
            state = guard.transition_state(repo, "state-test", state["revision"], "automated_passed")
            self.assertIsNone(state["candidate"])
            with self.assertRaises(guard.GuardError):
                guard.transition_state(repo, "state-test", state["revision"], "complete", manual_confirmed=True)
            state = guard.transition_state(repo, "state-test", state["revision"], "complete")
            self.assertEqual(state["manual_acceptance"], "not_required")

            state = guard.transition_state(repo, "state-test", state["revision"], "testing")
            state = guard.transition_state(repo, "state-test", state["revision"], "automated_passed", candidate_path=candidate, manual_required=True)
            state = guard.transition_state(repo, "state-test", state["revision"], "manual_pending")
            with self.assertRaises(guard.GuardError):
                guard.transition_state(repo, "state-test", state["revision"], "complete")
            state = guard.transition_state(repo, "state-test", state["revision"], "complete", manual_confirmed=True)
            self.assertEqual(state["manual_acceptance"], "passed")

            state = guard.update_state(repo, "state-test", state["revision"], active_children={"inherited-session": "solver"})
            state = guard.recover_state(repo, "state-test", state["revision"])
            self.assertEqual(state["phase"], "blocked")
            self.assertEqual(state["repository"], guard.repository_snapshot(repo))
            with self.assertRaises(guard.GuardError):
                guard.transition_state(repo, "state-test", state["revision"], "implementing")
            state = guard.update_state(repo, "state-test", state["revision"], active_children={}, next_action="select one writer")
            state = guard.transition_state(repo, "state-test", state["revision"], "implementing")
            self.assertEqual(state["phase"], "implementing")

    def test_invalid_task_slug_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init")
            with self.assertRaises(guard.GuardError):
                guard.init_state(repo, "../escape", "R0")

    def test_ignored_candidate_replacement_and_deletion_invalidate_acceptance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pro guard ignored candidate ") as tmp:
            base = Path(tmp)
            repo = base / "repository"
            repo.mkdir()
            git(repo, "init")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "Pro Guard Test")
            (repo / ".gitignore").write_text("candidate.bin\n", encoding="utf-8")
            (repo / "tracked.txt").write_text("fixture", encoding="utf-8")
            git(repo, "add", ".gitignore", "tracked.txt")
            git(repo, "commit", "-m", "fixture")
            candidate = repo / "candidate.bin"
            candidate.write_bytes(b"candidate-one")
            _, state = guard.init_state(repo, "ignored-candidate", "R0")
            state = guard.update_state(repo, "ignored-candidate", state["revision"], check={"name": "candidate", "status": "passed", "evidence": "verified"})
            state = guard.transition_state(repo, "ignored-candidate", state["revision"], "implementing")
            state = guard.transition_state(repo, "ignored-candidate", state["revision"], "testing")
            state = guard.transition_state(repo, "ignored-candidate", state["revision"], "automated_passed", candidate_path=candidate)
            original_status = state["repository"]["status_sha256"]
            candidate.write_bytes(b"candidate-two")
            self.assertEqual(original_status, guard.repository_snapshot(repo)["status_sha256"])
            state = guard.recover_state(repo, "ignored-candidate", state["revision"])
            self.assertEqual(state["phase"], "testing")
            self.assertEqual(state["automated_acceptance"], "stale")
            self.assertEqual(state["manual_acceptance"], "stale")
            self.assertEqual(state["checks"][0]["status"], "stale")
            self.assertIsNone(state["candidate"])

            state = guard.transition_state(repo, "ignored-candidate", state["revision"], "automated_passed", candidate_path=candidate)
            candidate.unlink()
            state = guard.recover_state(repo, "ignored-candidate", state["revision"])
            self.assertEqual(state["phase"], "testing")
            self.assertEqual(state["automated_acceptance"], "stale")
            self.assertIsNone(state["candidate"])

    def test_state_leaf_redirect_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pro guard state leaf ") as tmp:
            repo = Path(tmp)
            git(repo, "init")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "Pro Guard Test")
            (repo / "tracked.txt").write_text("fixture", encoding="utf-8")
            git(repo, "add", "tracked.txt")
            git(repo, "commit", "-m", "fixture")
            state_path, _ = guard.init_state(repo, "leaf-check", "R0")
            replacement = state_path.with_name("replacement.json")
            replacement.write_bytes(state_path.read_bytes())
            state_path.unlink()
            try:
                state_path.symlink_to(replacement)
            except OSError as exc:
                self.skipTest(f"platform does not permit symlink creation: {exc}")
            with self.assertRaises(guard.GuardError):
                guard.read_state(state_path, guard.load_policy())
            with self.assertRaises(guard.GuardError):
                guard.recover_state(repo, "leaf-check", 0)

    def test_state_leaf_redirect_boundary_is_checked_on_all_platforms(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pro guard mocked leaf ") as tmp:
            repo = Path(tmp)
            git(repo, "init")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "Pro Guard Test")
            (repo / "tracked.txt").write_text("fixture", encoding="utf-8")
            git(repo, "add", "tracked.txt")
            git(repo, "commit", "-m", "fixture")
            path, _ = guard.init_state(repo, "mocked-leaf", "R0")
            real_is_redirect = guard._is_redirect
            with mock.patch.object(guard, "_is_redirect", side_effect=lambda candidate: candidate == path or real_is_redirect(candidate)):
                with self.assertRaises(guard.GuardError):
                    guard.read_state(path, guard.load_policy())
                with self.assertRaises(guard.GuardError):
                    guard.recover_state(repo, "mocked-leaf", 0)

    def test_transaction_lock_contention_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pro guard lock ") as tmp:
            lock_path = Path(tmp) / "state.lock"
            with guard.TransactionLock(lock_path, timeout=0.1):
                with self.assertRaises(guard.GuardError):
                    with guard.TransactionLock(lock_path, timeout=0.05):
                        pass

    def test_linked_worktree_with_spaces_uses_git_metadata_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pro guard linked ") as tmp:
            base = Path(tmp)
            repo = base / "main repository"
            worktree = base / "linked worktree"
            repo.mkdir()
            git(repo, "init")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "Pro Guard Test")
            (repo / "tracked.txt").write_text("fixture", encoding="utf-8")
            git(repo, "add", "tracked.txt")
            git(repo, "commit", "-m", "fixture")
            git(repo, "worktree", "add", "-b", "codex/linked-guard", str(worktree))
            path, state = guard.init_state(worktree, "linked-state", "R0")
            self.assertTrue(path.is_file())
            self.assertNotEqual(Path(state["repository"]["git_dir"]), Path(state["repository"]["common_git_dir"]))
            self.assertFalse(str(path).startswith(str(worktree)))


if __name__ == "__main__":
    unittest.main()
