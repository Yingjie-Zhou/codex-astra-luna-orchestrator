#!/usr/bin/env python3
"""Fail-closed local evidence and resumable-state guard for Codex Pro v2.1.

This tool validates local rollout records and repository state.  It is not a
cryptographic attestation mechanism and cannot prove that local files were not
tampered with.
"""

import sys

if sys.version_info < (3, 11):
    print("pro_guard: Codex Pro v2.1 guard requires Python 3.11 or newer", file=sys.stderr)
    raise SystemExit(2)

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Any


class GuardError(RuntimeError):
    pass


SKILL_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = SKILL_ROOT / "policy.json"
TASK_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\Z")
HEX64_RE = re.compile(r"[0-9a-f]{64}\Z")
TOP_POLICY_KEYS = {
    "schema_version", "workflow_version", "python_minimum", "roles",
    "evidence_caps_utf8_bytes", "initial_bootstrap_turns_allowed", "state",
}
STATE_KEYS = {
    "schema_version", "workflow_version", "revision", "task", "risk", "phase",
    "repository", "active_children", "roles", "ownership", "checks", "next_action", "monitor",
    "candidate", "automated_acceptance", "manual_acceptance", "updated_at",
}
ATTESTATION_KEYS = {"attested", "session_id", "requested_role", "resolved_role", "model", "effort", "turn_id", "rollout", "limitation"}


def fail(message: str) -> None:
    raise GuardError(message)


def require_python() -> None:
    if sys.version_info < (3, 11):
        fail("Codex Pro v2.1 guard requires Python 3.11 or newer")


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"cannot load strict policy {path}: {exc}")
    if not isinstance(policy, dict) or set(policy) != TOP_POLICY_KEYS:
        fail("policy has missing or unknown top-level keys")
    if policy["schema_version"] != 1 or policy["workflow_version"] != "2.1":
        fail("unsupported policy version")
    if policy["python_minimum"] != [3, 11]:
        fail("policy Python minimum must be exactly 3.11")
    if not isinstance(policy["initial_bootstrap_turns_allowed"], int) or policy["initial_bootstrap_turns_allowed"] < 0:
        fail("invalid bootstrap-turn policy")
    roles = policy["roles"]
    expected_roles = {"root", "auditor", "explorer", "researcher", "worker", "tester", "solver", "reviewer", "reviewer_high"}
    if not isinstance(roles, dict) or set(roles) != expected_roles:
        fail("policy role set must use only the exact Pro v2.1 role names")
    for name, value in roles.items():
        if not isinstance(value, dict) or set(value) != {"model", "effort", "source"} or not all(isinstance(v, str) and v for v in value.values()):
            fail(f"invalid role policy for {name}")
    caps = policy["evidence_caps_utf8_bytes"]
    expected_caps = {"child_report": 8192, "forwarded_tool_excerpt": 20480, "root_phase_or_recovery_summary": 12288}
    if caps != expected_caps:
        fail("evidence caps differ from the Pro v2.1 contract")
    state = policy["state"]
    if not isinstance(state, dict) or set(state) != {"schema_version", "phases", "transitions"} or state["schema_version"] != 1:
        fail("invalid state policy")
    if set(state["transitions"]) != set(state["phases"]):
        fail("every phase must have an explicit transition list")
    return policy


def _run_git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True,
        text=not binary, check=False,
    )
    if result.returncode:
        stderr = result.stderr.decode(errors="replace") if binary else result.stderr
        fail(f"git {' '.join(args)} failed: {stderr.strip()}")
    return result.stdout if binary else result.stdout.strip()


def _iter_process_stdout(command: list[str], description: str):
    with tempfile.TemporaryFile(mode="w+b") as error_stream:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=error_stream)
        assert process.stdout is not None
        try:
            with process.stdout:
                while chunk := process.stdout.read(1024 * 1024):
                    yield chunk
            return_code = process.wait()
            if return_code != 0:
                error_stream.seek(0)
                diagnostic = error_stream.read(20480)
                truncated = bool(error_stream.read(1))
                message = diagnostic.decode(errors="replace").strip()
                if truncated:
                    message += " [stderr truncated at 20480 bytes]"
                fail(f"{description} failed ({return_code}): {message}")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def _hash_git_output(digest: Any, repo: Path, label: bytes, *args: str) -> None:
    digest.update(label)
    command = ["git", "-C", str(repo), *args]
    for chunk in _iter_process_stdout(command, f"git {' '.join(args)}"):
        digest.update(chunk)


def _iter_untracked_paths(repo: Path):
    command = ["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard", "-z"]
    pending = b""
    for chunk in _iter_process_stdout(command, "git ls-files"):
        pending += chunk
        parts = pending.split(b"\0")
        pending = parts.pop()
        yield from parts
    if pending:
        fail("git ls-files returned a malformed non-NUL-terminated path")


def repository_dirty_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    _hash_git_output(digest, root, b"status\0", "status", "--porcelain=v2", "-z", "--untracked-files=all")
    _hash_git_output(digest, root, b"index-diff\0", "diff", "--cached", "--binary", "--no-ext-diff", "--no-textconv")
    _hash_git_output(digest, root, b"worktree-diff\0", "diff", "--binary", "--no-ext-diff", "--no-textconv")
    root_absolute = root.absolute()
    for raw_path in _iter_untracked_paths(root):
        relative = Path(os.fsdecode(raw_path))
        if relative.is_absolute() or ".." in relative.parts:
            fail(f"unsafe untracked path from Git: {relative}")
        path = root_absolute / relative
        try:
            path.absolute().relative_to(root_absolute)
            metadata = path.lstat()
        except (OSError, ValueError) as exc:
            fail(f"cannot safely fingerprint untracked path {relative}: {exc}")
        digest.update(b"untracked\0" + len(raw_path).to_bytes(8, "big") + raw_path)
        file_type = stat.S_IFMT(metadata.st_mode)
        digest.update(file_type.to_bytes(8, "big"))
        if stat.S_ISLNK(metadata.st_mode):
            target = os.fsencode(os.readlink(path))
            digest.update(len(target).to_bytes(8, "big") + target)
        elif stat.S_ISREG(metadata.st_mode):
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            try:
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode):
                    fail(f"untracked path changed type while hashing: {relative}")
                digest.update(opened.st_size.to_bytes(8, "big"))
                while chunk := os.read(descriptor, 1024 * 1024):
                    digest.update(chunk)
            finally:
                os.close(descriptor)
        else:
            digest.update(str(metadata.st_size).encode("ascii"))
    return digest.hexdigest()


def _is_redirect(path: Path) -> bool:
    try:
        stat = path.lstat()
    except OSError as exc:
        fail(f"cannot inspect {path}: {exc}")
    if path.is_symlink():
        return True
    return bool(getattr(stat, "st_file_attributes", 0) & 0x400)


def reject_redirects(path: Path, stop: Path | None = None) -> None:
    path = path.absolute()
    stop = stop.absolute() if stop else Path(path.anchor)
    current = path
    while True:
        if current.exists() and _is_redirect(current):
            fail(f"symbolic-link/reparse redirect is not allowed: {current}")
        if current == stop or current.parent == current:
            break
        current = current.parent


def canonical_contained(path: Path, roots: list[Path], *, must_exist: bool = True) -> Path:
    if must_exist and not path.exists():
        fail(f"path does not exist: {path}")
    reject_redirects(path)
    resolved = path.resolve(strict=must_exist)
    for root in roots:
        root_resolved = root.resolve(strict=True)
        reject_redirects(root)
        try:
            resolved.relative_to(root_resolved)
            return resolved
        except ValueError:
            pass
    fail(f"path escapes the allowed roots: {path}")


def repository_snapshot(repo: Path) -> dict[str, str]:
    reject_redirects(repo.absolute())
    root = Path(str(_run_git(repo, "rev-parse", "--show-toplevel"))).resolve(strict=True)
    common_raw = Path(str(_run_git(root, "rev-parse", "--git-common-dir")))
    common = (root / common_raw).resolve(strict=True) if not common_raw.is_absolute() else common_raw.resolve(strict=True)
    git_raw = Path(str(_run_git(root, "rev-parse", "--git-dir")))
    git_dir = (root / git_raw).resolve(strict=True) if not git_raw.is_absolute() else git_raw.resolve(strict=True)
    reject_redirects(root)
    reject_redirects(common)
    reject_redirects(git_dir)
    return {
        "root": str(root),
        "common_git_dir": str(common),
        "git_dir": str(git_dir),
        "identity": hashlib.sha256(str(common).encode("utf-8")).hexdigest(),
        "branch": str(_run_git(root, "rev-parse", "--abbrev-ref", "HEAD")),
        "head": str(_run_git(root, "rev-parse", "HEAD")),
        "status_sha256": repository_dirty_fingerprint(root),
    }


def require_recovered(repo: Path, state: dict[str, Any]) -> dict[str, str]:
    current = repository_snapshot(repo)
    previous = state["repository"]
    for key in ("root", "identity", "branch", "head", "status_sha256"):
        if current[key] != previous[key]:
            fail(f"repository {key} changed; run state-recover before mutating state")
    return current


def state_path(repo: Path, task: str) -> Path:
    if not TASK_RE.fullmatch(task):
        fail("task slug must be 1-64 lowercase letters, digits, or interior hyphens")
    snapshot = repository_snapshot(repo)
    raw = Path(str(_run_git(repo, "rev-parse", "--git-path", f"codex-tasks/{task}/state.json")))
    root = Path(snapshot["root"])
    result = (root / raw).absolute() if not raw.is_absolute() else raw.absolute()
    allowed = [Path(snapshot["common_git_dir"]), Path(snapshot["git_dir"])]
    parent = canonical_contained(result.parent, allowed, must_exist=False)
    return parent / "state.json"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


class TransactionLock:
    def __init__(self, path: Path, timeout: float = 10.0):
        self.path = path
        self.timeout = timeout
        self.fd: int | None = None
        self.identity: os.stat_result | None = None

    def __enter__(self) -> "TransactionLock":
        deadline = time.monotonic() + self.timeout
        self.path.parent.mkdir(parents=True, exist_ok=True)
        reject_redirects(self.path.parent)
        while True:
            try:
                if os.path.lexists(self.path):
                    reject_redirects(self.path)
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                self.identity = os.fstat(self.fd)
                if not stat.S_ISREG(self.identity.st_mode):
                    fail(f"transaction lock is not a regular file: {self.path}")
                os.write(self.fd, json.dumps({"pid": os.getpid(), "created_at": utc_now()}).encode("utf-8"))
                os.fsync(self.fd)
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    fail(f"transaction lock is already held: {self.path}")
                time.sleep(0.05)

    def __exit__(self, *_: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
        try:
            if self.identity is not None and not os.path.samestat(self.identity, self.path.lstat()):
                fail(f"transaction lock changed identity while held: {self.path}")
            self.path.unlink()
        except FileNotFoundError:
            pass


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    reject_redirects(path.parent)
    if os.path.lexists(path):
        reject_redirects(path)
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            fail(f"temporary state target is not a regular file: {temporary}")
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if os.path.lexists(path):
            reject_redirects(path)
        if _is_redirect(Path(temporary)):
            fail(f"temporary state target became a redirect: {temporary}")
        os.replace(temporary, path)
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def validate_evidence(value: object, kind: str, repo: Path, policy: dict[str, Any]) -> dict[str, Any] | str:
    cap = policy["evidence_caps_utf8_bytes"].get(kind)
    if not isinstance(cap, int):
        fail(f"unknown evidence kind: {kind}")
    if isinstance(value, str):
        size = len(value.encode("utf-8"))
        if size > cap:
            fail(f"{kind} is {size} UTF-8 bytes; cap is {cap}; store it and use a path+digest reference")
        return value
    if not isinstance(value, dict) or set(value) != {"path", "sha256", "bytes"}:
        fail("oversize evidence replacement must contain exactly path, sha256, and bytes")
    if not isinstance(value["path"], str) or not isinstance(value["bytes"], int) or not isinstance(value["sha256"], str):
        fail("invalid evidence replacement types")
    path = canonical_contained((repo / value["path"]).absolute(), [repo], must_exist=True)
    if not path.is_file():
        fail("evidence replacement path must be a regular file")
    content = path.read_bytes()
    if len(content) != value["bytes"] or hashlib.sha256(content).hexdigest() != value["sha256"] or not HEX64_RE.fullmatch(value["sha256"]):
        fail("evidence replacement size or digest mismatch")
    return value


def _profile_codex_root(profile_root: Path | None) -> Path:
    root = profile_root if profile_root is not None else SKILL_ROOT.parents[2]
    installed = root / ".codex"
    source = root / "codex"
    matches = [candidate for candidate in (installed, source) if candidate.is_dir()]
    if len(matches) != 1:
        fail(f"profile root must contain exactly one of .codex or codex; found {len(matches)}")
    reject_redirects(matches[0])
    return matches[0]


def _expected_role(role: str, policy: dict[str, Any], profile_root: Path | None) -> tuple[str, str]:
    if role not in policy["roles"]:
        fail(f"unknown exact role name: {role}")
    codex = _profile_codex_root(profile_root)
    source = codex / ("config.toml" if role == "root" else f"agents/{role}.toml")
    try:
        with source.open("rb") as stream:
            config = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        fail(f"cannot read role configuration {source}: {exc}")
    model, effort = config.get("model"), config.get("model_reasoning_effort")
    declared = policy["roles"][role]
    if model != declared["model"] or effort != declared["effort"]:
        fail(f"role configuration differs from strict policy for {role}")
    return model, effort


def attest_rollout(rollout: Path, session_id: str, requested_role: str, *, profile_root: Path | None = None, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    if not session_id:
        fail("a full nonempty session/thread ID is required")
    if requested_role == "root":
        expected_names = {"root"}
    elif requested_role in policy["roles"]:
        expected_names = {requested_role}
    else:
        fail(f"unknown exact role name: {requested_role}")
    paths = [rollout] if rollout.is_file() else sorted(rollout.rglob("*.jsonl")) if rollout.is_dir() else []
    matches: list[tuple[Path, dict[str, Any], list[dict[str, Any]]]] = []
    for path in paths:
        session: dict[str, Any] | None = None
        active = False
        turns: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            fail(f"cannot read rollout {path}: {exc}")
        for line_number, line in enumerate(lines, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                fail(f"malformed rollout JSON {path}:{line_number}: {exc}")
            if not isinstance(record, dict) or not {"type", "payload", "timestamp"}.issubset(record) or not isinstance(record.get("payload"), dict) or not isinstance(record.get("type"), str):
                fail(f"malformed rollout record {path}:{line_number}")
            payload = record["payload"]
            if record["type"] == "session_meta":
                child_path = payload.get("agent_path")
                child_id = payload.get("id")
                parent_session = payload.get("session_id")
                parent_thread = payload.get("parent_thread_id")
                if child_path not in (None, ""):
                    if not isinstance(child_id, str) or not child_id:
                        fail(f"subagent session_meta lacks an authoritative child id at {path}:{line_number}")
                    if parent_session is not None and parent_thread is not None and parent_session != parent_thread:
                        fail(f"inconsistent subagent parent chain at {path}:{line_number}")
                    candidate = child_id
                else:
                    if not isinstance(child_id, str) or not child_id:
                        fail(f"root session_meta lacks an authoritative id at {path}:{line_number}")
                    if parent_session is not None and parent_session != child_id:
                        fail(f"root id/session_id mismatch at {path}:{line_number}")
                    if parent_thread is not None:
                        fail(f"root session_meta unexpectedly has parent_thread_id at {path}:{line_number}")
                    candidate = child_id
                active = candidate == session_id
                if candidate == session_id:
                    if session is not None:
                        fail(f"duplicate session_meta for {session_id} in {path}")
                    session = payload
            elif record["type"] == "turn_context" and session is not None and active:
                required_turn = {"turn_id", "model", "effort", "cwd", "workspace_roots", "approval_policy", "sandbox_policy"}
                if not required_turn.issubset(payload):
                    fail(f"incomplete authoritative turn_context {path}:{line_number}")
                owner = payload.get("session_id", session_id)
                if owner == session_id:
                    turns.append(payload)
        if session is not None:
            matches.append((path, session, turns))
    if len(matches) != 1:
        fail(f"expected one unambiguous rollout for session {session_id}, found {len(matches)}")
    path, session, turns = matches[0]
    direct_role_fields = [session.get(key) for key in ("agent_role", "name") if session.get(key) is not None]
    source_meta = session.get("source")
    subagent_meta = source_meta.get("subagent") if isinstance(source_meta, dict) else None
    spawn_meta = subagent_meta.get("thread_spawn") if isinstance(subagent_meta, dict) else None
    nested_role = spawn_meta.get("agent_role") if isinstance(spawn_meta, dict) else None
    if nested_role is not None:
        direct_role_fields.append(nested_role)
    if requested_role == "root":
        if session.get("thread_source") != "user" or session.get("agent_path") not in (None, ""):
            fail("root attestation requires a user/root thread with no child agent_path")
        if any(value != "root" for value in direct_role_fields):
            fail("non-null root role metadata conflicts with root")
        resolved_role = "root"
    else:
        agent_path = session.get("agent_path")
        if agent_path != f"/root/{requested_role}" or not re.fullmatch(r"/root/[a-z0-9_]+", str(agent_path)):
            fail(f"requested role {requested_role!r} has non-canonical agent_path {agent_path!r}")
        if any(value != requested_role for value in direct_role_fields):
            fail(f"non-null role metadata conflicts with requested role {requested_role!r}")
        resolved_role = requested_role
    if not turns:
        fail("rollout has no authoritative turn_context for the session")
    expected_model, expected_effort = _expected_role(requested_role, policy, profile_root)
    relevant = turns[policy["initial_bootstrap_turns_allowed"]:]
    if not relevant:
        fail("bootstrap allowance removed every authoritative turn")
    for index, turn in enumerate(relevant):
        if not isinstance(turn.get("turn_id"), str) or not turn["turn_id"]:
            fail(f"turn_context {index} has no authoritative turn_id")
        if turn.get("model") != expected_model or turn.get("effort") != expected_effort:
            fail(f"turn_context {index} model/effort mismatch: observed {turn.get('model')}/{turn.get('effort')}, expected {expected_model}/{expected_effort}")
    final = relevant[-1]
    return {
        "attested": True, "session_id": session_id, "requested_role": requested_role,
        "resolved_role": resolved_role, "model": final["model"], "effort": final["effort"],
        "turn_id": final.get("turn_id"), "rollout": str(path.resolve()),
        "limitation": "local evidence validation only; not cryptographic or tamper-proof",
    }


def record_role_state(repo: Path, task: str, expected_revision: int, attestation_path: Path, *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    path = state_path(repo, task)
    try:
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"cannot read attestation: {exc}")
    if not isinstance(attestation, dict) or set(attestation) != ATTESTATION_KEYS or attestation.get("attested") is not True:
        fail("invalid attestation record")
    role = attestation.get("requested_role")
    if role not in policy["roles"] or attestation.get("resolved_role") != role:
        fail("attestation does not bind an exact policy role")
    declared = policy["roles"][role]
    if attestation.get("model") != declared["model"] or attestation.get("effort") != declared["effort"]:
        fail("attestation model/effort differs from policy")
    with TransactionLock(path.with_suffix(".lock")):
        state = read_state(path, policy)
        if state["revision"] != expected_revision:
            fail(f"revision CAS mismatch: expected {expected_revision}, actual {state['revision']}")
        require_recovered(repo, state)
        state["roles"][role] = attestation
        state["active_children"].pop(attestation["session_id"], None)
        state["revision"] += 1
        state["updated_at"] = utc_now()
        validate_state(state, policy)
        _atomic_write(path, state)
    return state


def update_state(repo: Path, task: str, expected_revision: int, *, active_children: dict[str, str] | None = None, ownership: dict[str, str] | None = None, check: dict[str, Any] | None = None, next_action: str | None = None, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    path = state_path(repo, task)
    with TransactionLock(path.with_suffix(".lock")):
        state = read_state(path, policy)
        if state["revision"] != expected_revision:
            fail(f"revision CAS mismatch: expected {expected_revision}, actual {state['revision']}")
        require_recovered(repo, state)
        if active_children is not None:
            state["active_children"] = active_children
        if ownership is not None:
            state["ownership"] = ownership
        if check is not None:
            if not isinstance(check, dict) or set(check) != {"name", "status", "evidence"}:
                fail("check must contain exactly name, status, and evidence")
            check["evidence"] = validate_evidence(check["evidence"], "root_phase_or_recovery_summary", Path(state["repository"]["root"]), policy)
            state["checks"].append(check)
        if next_action is not None:
            state["next_action"] = next_action
        state["revision"] += 1
        state["updated_at"] = utc_now()
        validate_state(state, policy)
        _atomic_write(path, state)
    return state


def _require_roles_for_phase(state: dict[str, Any], phase: str) -> None:
    risk = state["risk"]
    roles = set(state["roles"])
    required: set[str] = set()
    if phase in {"audited", "designed", "implementing", "testing", "reviewing", "automated_passed", "manual_pending", "complete"} and risk != "R0":
        required.add("auditor")
    if risk in {"R2", "R3"} and phase in {"implementing", "testing", "reviewing", "automated_passed", "manual_pending", "complete"}:
        required.add("explorer")
    if risk == "R3" and phase in {"designed", "implementing", "testing", "reviewing", "automated_passed", "manual_pending", "complete"}:
        required.add("reviewer")
    if phase in {"testing", "reviewing", "automated_passed", "manual_pending", "complete"}:
        if risk == "R0":
            required.add("root")
        elif risk == "R1":
            if not ({"root", "worker"} & roles):
                required.add("worker")
        elif risk == "R2":
            if not ({"worker", "solver"} & roles):
                required.add("worker")
        else:
            required.add("solver")
    if phase in {"automated_passed", "manual_pending", "complete"}:
        if risk != "R0":
            required.add("tester")
        if risk == "R2":
            required.add("reviewer")
        if risk == "R3":
            required.add("reviewer_high")
    missing = sorted(required - roles)
    if missing:
        fail(f"phase {phase} is missing required exact-role attestations: {', '.join(missing)}")
    if phase in {"automated_passed", "manual_pending", "complete"} and state.get("active_children"):
        fail(f"phase {phase} requires every active child to finish or explicitly fail")


def validate_state(state: object, policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(state, dict) or set(state) != STATE_KEYS:
        fail("state has missing or unknown keys")
    if state["schema_version"] != 1 or state["workflow_version"] != "2.1":
        fail("unsupported state version")
    if not isinstance(state["revision"], int) or state["revision"] < 0:
        fail("state revision must be a nonnegative integer")
    if not isinstance(state["task"], str) or not TASK_RE.fullmatch(state["task"]):
        fail("invalid task slug in state")
    if state["risk"] not in {"R0", "R1", "R2", "R3"} or state["phase"] not in policy["state"]["phases"]:
        fail("invalid risk or phase")
    repository = state["repository"]
    if not isinstance(repository, dict) or set(repository) != {"root", "common_git_dir", "git_dir", "identity", "branch", "head", "status_sha256"}:
        fail("invalid repository snapshot")
    for key in ("identity", "status_sha256"):
        if not isinstance(repository[key], str) or not HEX64_RE.fullmatch(repository[key]):
            fail(f"invalid repository {key}")
    if not all(isinstance(repository[key], str) and repository[key] for key in repository):
        fail("repository snapshot fields must be nonempty strings")
    if not isinstance(state["roles"], dict) or not set(state["roles"]).issubset(policy["roles"]):
        fail("invalid exact-role attestation map")
    for role, attestation in state["roles"].items():
        expected = policy["roles"][role]
        if not isinstance(attestation, dict) or set(attestation) != ATTESTATION_KEYS or attestation.get("requested_role") != role or attestation.get("resolved_role") != role or attestation.get("attested") is not True or attestation.get("model") != expected["model"] or attestation.get("effort") != expected["effort"]:
            fail(f"invalid stored attestation for {role}")
    if not isinstance(state["active_children"], dict) or not all(isinstance(session_id, str) and session_id and role in set(policy["roles"]) - {"root"} for session_id, role in state["active_children"].items()):
        fail("active_children must map full session IDs to exact custom roles")
    if not isinstance(state["ownership"], dict) or not all(isinstance(key, str) and key and isinstance(value, str) and value in policy["roles"] for key, value in state["ownership"].items()):
        fail("ownership must map nonempty paths to exact roles")
    if not isinstance(state["checks"], list) or not all(isinstance(item, dict) and set(item) == {"name", "status", "evidence"} and isinstance(item["name"], str) and item["name"] and item["status"] in {"passed", "failed", "stale"} for item in state["checks"]):
        fail("invalid roles, ownership, or checks")
    for item in state["checks"]:
        validate_evidence(item["evidence"], "root_phase_or_recovery_summary", Path(repository["root"]), policy)
    if not isinstance(state["next_action"], str) or not state["next_action"]:
        fail("next_action must be a nonempty string")
    monitor = state["monitor"]
    if not isinstance(monitor, dict) or set(monitor) != {"deadline", "remaining_budget"} or isinstance(monitor["remaining_budget"], bool) or not isinstance(monitor["remaining_budget"], int) or monitor["remaining_budget"] < 0:
        fail("monitor requires a persisted deadline and finite nonnegative budget")
    if monitor["deadline"] is not None:
        try:
            parsed_deadline = dt.datetime.fromisoformat(str(monitor["deadline"]).replace("Z", "+00:00"))
        except ValueError:
            fail("invalid monitor deadline")
        if parsed_deadline.tzinfo is None:
            fail("monitor deadline must include a timezone")
    candidate = state["candidate"]
    if candidate is not None:
        required = {"path", "sha256", "bytes", "status_sha256"}
        if not isinstance(candidate, dict) or set(candidate) != required or not HEX64_RE.fullmatch(str(candidate.get("sha256", ""))) or not HEX64_RE.fullmatch(str(candidate.get("status_sha256", ""))):
            fail("invalid candidate binding")
    if state["automated_acceptance"] not in {"not_run", "passed", "stale"} or state["manual_acceptance"] not in {"not_required", "pending", "passed", "stale"}:
        fail("invalid acceptance status")
    if state["phase"] in {"automated_passed", "manual_pending", "complete"} and state["automated_acceptance"] != "passed":
        fail("acceptance phase requires passed automated acceptance")
    if state["phase"] == "manual_pending" and state["manual_acceptance"] != "pending":
        fail("manual_pending phase requires pending manual acceptance")
    if state["manual_acceptance"] in {"pending", "passed"} and state["candidate"] is None:
        fail("manual acceptance requires a bound candidate")
    if state["phase"] == "complete" and state["manual_acceptance"] not in {"not_required", "passed"}:
        fail("complete phase requires no manual gate or explicit manual pass")
    try:
        updated = dt.datetime.fromisoformat(str(state["updated_at"]).replace("Z", "+00:00"))
    except ValueError:
        fail("updated_at must be an ISO-8601 timestamp")
    if updated.tzinfo is None:
        fail("updated_at must include a timezone")
    return state


def read_state(path: Path, policy: dict[str, Any]) -> dict[str, Any]:
    try:
        reject_redirects(path)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                fail(f"state leaf is not a regular file: {path}")
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                descriptor = -1
                value = json.load(stream)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"cannot read state {path}: {exc}")
    return validate_state(value, policy)


def init_state(repo: Path, task: str, risk: str, *, deadline: str | None = None, budget: int = 0, policy: dict[str, Any] | None = None) -> tuple[Path, dict[str, Any]]:
    policy = policy or load_policy()
    path = state_path(repo, task)
    with TransactionLock(path.with_suffix(".lock")):
        if os.path.lexists(path):
            reject_redirects(path)
            fail(f"state already exists: {path}")
        snapshot = repository_snapshot(repo)
        state = {
            "schema_version": 1, "workflow_version": "2.1", "revision": 0,
            "task": task, "risk": risk, "phase": "draft", "repository": snapshot,
            "active_children": {}, "roles": {}, "ownership": {}, "checks": [], "next_action": "complete audit gate",
            "monitor": {"deadline": deadline, "remaining_budget": budget}, "candidate": None,
            "automated_acceptance": "not_run", "manual_acceptance": "not_required", "updated_at": utc_now(),
        }
        validate_state(state, policy)
        _atomic_write(path, state)
    return path, state


def _stream_file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _candidate(repo: Path, candidate_path: Path, status_sha256: str) -> dict[str, Any]:
    root = Path(repository_snapshot(repo)["root"])
    path = canonical_contained(candidate_path.absolute(), [root], must_exist=True)
    if not path.is_file():
        fail("candidate must be a regular file inside the repository")
    digest, size = _stream_file_digest(path)
    return {"path": str(path.relative_to(root)), "sha256": digest, "bytes": size, "status_sha256": status_sha256}


def _candidate_is_current(repo: Path, candidate: dict[str, Any], snapshot: dict[str, str]) -> bool:
    if candidate["status_sha256"] != snapshot["status_sha256"]:
        return False
    root = Path(snapshot["root"])
    try:
        path = canonical_contained((root / candidate["path"]).absolute(), [root], must_exist=True)
        digest, size = _stream_file_digest(path)
    except (GuardError, OSError):
        return False
    return size == candidate["bytes"] and digest == candidate["sha256"]


def transition_state(repo: Path, task: str, expected_revision: int, phase: str, *, candidate_path: Path | None = None, manual_required: bool = False, manual_confirmed: bool = False, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    path = state_path(repo, task)
    with TransactionLock(path.with_suffix(".lock")):
        state = read_state(path, policy)
        if state["revision"] != expected_revision:
            fail(f"revision CAS mismatch: expected {expected_revision}, actual {state['revision']}")
        if phase not in policy["state"]["transitions"][state["phase"]]:
            fail(f"illegal state transition {state['phase']} -> {phase}")
        if manual_confirmed and not (phase == "complete" and state["phase"] == "manual_pending"):
            fail("--manual-confirmed is only valid for manual_pending -> complete")
        if manual_required and phase != "automated_passed":
            fail("--manual-required is only valid for automated_passed")
        if candidate_path is not None and phase != "automated_passed":
            fail("--candidate is only valid for automated_passed")
        if state["phase"] == "blocked" and state["active_children"]:
            fail("blocked recovery state requires explicit active_children reconciliation before transition")
        if state["phase"] == "draft" and phase == "implementing" and state["risk"] != "R0":
            fail("only R0 may move directly from draft to implementing")
        if phase == "designed" and state["risk"] != "R3":
            fail("designed phase is reserved for R3")
        _require_roles_for_phase(state, phase)
        snapshot = require_recovered(repo, state)
        if state["automated_acceptance"] == "passed" and state["candidate"] is not None and not _candidate_is_current(repo, state["candidate"], snapshot):
            fail("candidate or dirty fingerprint changed; recover state before continuing")
        state["repository"] = snapshot
        if phase == "automated_passed":
            if manual_required and candidate_path is None:
                fail("manual-required automated_passed requires a candidate path and digest binding")
            state["candidate"] = _candidate(repo, candidate_path, snapshot["status_sha256"]) if candidate_path is not None else None
            state["automated_acceptance"] = "passed"
            state["manual_acceptance"] = "pending" if manual_required else "not_required"
        elif phase == "manual_pending":
            if state["candidate"] is None or state["manual_acceptance"] != "pending":
                fail("manual_pending requires a bound candidate and pending manual gate")
        elif phase == "complete":
            if state["manual_acceptance"] == "pending":
                if state["phase"] != "manual_pending":
                    fail("required manual acceptance must pass through manual_pending")
                if not manual_confirmed:
                    fail("manual_pending -> complete requires explicit --manual-confirmed")
                state["manual_acceptance"] = "passed"
        state["phase"] = phase
        state["revision"] += 1
        state["updated_at"] = utc_now()
        validate_state(state, policy)
        _atomic_write(path, state)
    return state


def recover_state(repo: Path, task: str, expected_revision: int, *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    path = state_path(repo, task)
    with TransactionLock(path.with_suffix(".lock")):
        state = read_state(path, policy)
        if state["revision"] != expected_revision:
            fail(f"revision CAS mismatch: expected {expected_revision}, actual {state['revision']}")
        current = repository_snapshot(repo)
        previous = state["repository"]
        if current["identity"] != previous["identity"] or current["root"] != previous["root"]:
            fail("recovery repository identity mismatch")
        changed = any(current[key] != previous[key] for key in ("branch", "head", "status_sha256"))
        candidate_changed = state["candidate"] is not None and not _candidate_is_current(repo, state["candidate"], current)
        if changed or candidate_changed:
            for check in state["checks"]:
                if check["status"] == "passed":
                    check["status"] = "stale"
        if (changed or candidate_changed) and (state["automated_acceptance"] == "passed" or state["manual_acceptance"] in {"pending", "passed"}):
            state["automated_acceptance"] = "stale"
            state["manual_acceptance"] = "stale"
            state["candidate"] = None
            state["phase"] = "testing"
            state["next_action"] = "re-run automated evidence and any required manual acceptance after repository/candidate change"
        if state["active_children"]:
            if state["automated_acceptance"] == "passed" or state["manual_acceptance"] in {"pending", "passed"}:
                state["automated_acceptance"] = "stale"
                state["manual_acceptance"] = "stale"
                state["candidate"] = None
            state["phase"] = "blocked"
            state["next_action"] = "reconcile inherited active_children, then explicitly clear them before selecting a writer"
        state["repository"] = current
        state["revision"] += 1
        state["updated_at"] = utc_now()
        validate_state(state, policy)
        _atomic_write(path, state)
    return state


def monitor_tick(repo: Path, task: str, expected_revision: int, *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_policy()
    path = state_path(repo, task)
    with TransactionLock(path.with_suffix(".lock")):
        state = read_state(path, policy)
        if state["revision"] != expected_revision:
            fail(f"revision CAS mismatch: expected {expected_revision}, actual {state['revision']}")
        require_recovered(repo, state)
        if state["monitor"]["remaining_budget"] <= 0:
            fail("monitor budget exhausted")
        deadline = state["monitor"]["deadline"]
        if deadline is None:
            fail("monitor deadline is required before consuming budget")
        parsed = dt.datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        if parsed <= dt.datetime.now(dt.timezone.utc):
            fail("monitor deadline has expired")
        state["monitor"]["remaining_budget"] -= 1
        state["revision"] += 1
        state["updated_at"] = utc_now()
        validate_state(state, policy)
        _atomic_write(path, state)
    return state


def main(argv: list[str] | None = None) -> int:
    require_python()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    attest = commands.add_parser("attest")
    attest.add_argument("--rollout", type=Path, required=True)
    attest.add_argument("--session", required=True)
    attest.add_argument("--role", required=True)
    attest.add_argument("--profile-root", type=Path)
    init = commands.add_parser("state-init")
    init.add_argument("--repo", type=Path, required=True)
    init.add_argument("--task", required=True)
    init.add_argument("--risk", required=True)
    init.add_argument("--deadline")
    init.add_argument("--budget", type=int, default=0)
    transition = commands.add_parser("state-transition")
    transition.add_argument("--repo", type=Path, required=True)
    transition.add_argument("--task", required=True)
    transition.add_argument("--expected-revision", type=int, required=True)
    transition.add_argument("--phase", required=True)
    transition.add_argument("--candidate", type=Path)
    transition.add_argument("--manual-required", action="store_true")
    transition.add_argument("--manual-confirmed", action="store_true")
    role = commands.add_parser("state-record-role")
    role.add_argument("--repo", type=Path, required=True)
    role.add_argument("--task", required=True)
    role.add_argument("--expected-revision", type=int, required=True)
    role.add_argument("--attestation", type=Path, required=True)
    update = commands.add_parser("state-update")
    update.add_argument("--repo", type=Path, required=True)
    update.add_argument("--task", required=True)
    update.add_argument("--expected-revision", type=int, required=True)
    update.add_argument("--active-children", type=Path, help="JSON object mapping full session IDs to exact roles")
    update.add_argument("--ownership", type=Path, help="JSON object mapping paths to exact writer roles")
    update.add_argument("--check", type=Path, help="JSON check record with bounded evidence")
    update.add_argument("--next-action")
    recover = commands.add_parser("state-recover")
    recover.add_argument("--repo", type=Path, required=True)
    recover.add_argument("--task", required=True)
    recover.add_argument("--expected-revision", type=int, required=True)
    monitor = commands.add_parser("monitor-tick")
    monitor.add_argument("--repo", type=Path, required=True)
    monitor.add_argument("--task", required=True)
    monitor.add_argument("--expected-revision", type=int, required=True)
    evidence = commands.add_parser("evidence-check")
    evidence.add_argument("--repo", type=Path, required=True)
    evidence.add_argument("--kind", required=True)
    evidence_source = evidence.add_mutually_exclusive_group(required=True)
    evidence_source.add_argument("--file", type=Path)
    evidence_source.add_argument("--reference", type=Path, help="JSON file containing path, sha256, and bytes")
    args = parser.parse_args(argv)
    policy = load_policy(args.policy)
    if args.command == "attest":
        result = attest_rollout(args.rollout, args.session, args.role, profile_root=args.profile_root, policy=policy)
    elif args.command == "state-init":
        path, state = init_state(args.repo, args.task, args.risk, deadline=args.deadline, budget=args.budget, policy=policy)
        result = {"path": str(path), "state": state}
    elif args.command == "state-transition":
        result = transition_state(args.repo, args.task, args.expected_revision, args.phase, candidate_path=args.candidate, manual_required=args.manual_required, manual_confirmed=args.manual_confirmed, policy=policy)
    elif args.command == "state-record-role":
        result = record_role_state(args.repo, args.task, args.expected_revision, args.attestation, policy=policy)
    elif args.command == "state-update":
        def load_optional_json(source: Path | None) -> Any:
            if source is None:
                return None
            try:
                return json.loads(source.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                fail(f"cannot read state update JSON {source}: {exc}")
        result = update_state(args.repo, args.task, args.expected_revision, active_children=load_optional_json(args.active_children), ownership=load_optional_json(args.ownership), check=load_optional_json(args.check), next_action=args.next_action, policy=policy)
    elif args.command == "state-recover":
        result = recover_state(args.repo, args.task, args.expected_revision, policy=policy)
    elif args.command == "monitor-tick":
        result = monitor_tick(args.repo, args.task, args.expected_revision, policy=policy)
    else:
        if args.reference:
            try:
                value = json.loads(args.reference.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                fail(f"cannot read evidence reference: {exc}")
        else:
            try:
                value = args.file.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                fail(f"cannot read inline evidence: {exc}")
        result = {"valid": True, "value": validate_evidence(value, args.kind, args.repo.resolve(), policy)}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GuardError as exc:
        print(f"pro_guard: {exc}", file=sys.stderr)
        raise SystemExit(2)
