from __future__ import annotations

import re
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
POWERSHELL_SETUP = REPOSITORY_ROOT / "setup.ps1"
POSIX_SETUP = REPOSITORY_ROOT / "setup.sh"
LEGACY_NAMES = {
    "local_deepseek_runner.py",
    "models.json",
    "run-deepseek-role.ps1",
    "start-ustc-adapter.ps1",
    "start-ustc-adapter.sh",
    "ustc_chat_adapter.py",
}
MANAGED_BLOCK_BEGIN = "<!-- BEGIN CODEX PRO WORKFLOW -->"
MANAGED_BLOCK_END = "<!-- END CODEX PRO WORKFLOW -->"
UTF8_BOM = b"\xef\xbb\xbf"


def available_installers() -> list[tuple[str, list[str]]]:
    installers: list[tuple[str, list[str]]] = []
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell:
        installers.append(
            (
                "powershell",
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(POWERSHELL_SETUP),
                ],
            )
        )
    shell = shutil.which("sh")
    if shell:
        installers.append(("posix", [shell, str(POSIX_SETUP)]))
    return installers


def invoke_installer(
    command: list[str], target: Path, answers_after_target: str
) -> subprocess.CompletedProcess[str]:
    answers = f"{installer_input_path(command, target)}\n{answers_after_target}"
    is_windows_sh = os.name == "nt" and Path(command[0]).name.lower() in {
        "sh",
        "sh.exe",
    }
    if is_windows_sh:
        raw = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            input=answers.encode("utf-8"),
            capture_output=True,
            timeout=30,
            check=False,
        )
        return subprocess.CompletedProcess(
            raw.args,
            raw.returncode,
            raw.stdout.decode("utf-8", errors="replace"),
            raw.stderr.decode("utf-8", errors="replace"),
        )
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        input=answers,
        text=True,
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    )


def run_installer_with_answers(
    command: list[str], target: Path, answers_after_target: str
) -> subprocess.CompletedProcess[str]:
    result = invoke_installer(command, target, answers_after_target)
    if result.returncode != 0:
        raise AssertionError(
            f"installer failed ({result.returncode})\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def installer_input_path(command: list[str], target: Path) -> str:
    if os.name == "nt" and Path(command[0]).name.lower() in {"sh", "sh.exe"}:
        posix = target.as_posix()
        drive, remainder = posix.split(":", 1)
        return f"/{drive.lower()}{remainder}"
    return target.as_posix()


def run_installer(command: list[str], target: Path, cleanup_answer: str) -> None:
    run_installer_with_answers(
        command,
        target,
        f"\n\ny\n{cleanup_answer}\nn\nn\n",
    )


def write_with_newlines(
    path: Path, text: str, newline: str, *, bom: bool = False
) -> None:
    normalized = text.replace("\r\n", "\n")
    data = normalized.replace("\n", newline).encode("utf-8")
    path.write_bytes((UTF8_BOM if bom else b"") + data)


def make_posix_source(directory: Path, newline: str, *, bom: bool) -> Path:
    source = directory / "source"
    source.mkdir()
    shutil.copy2(POSIX_SETUP, source / "setup.sh")
    instructions = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    write_with_newlines(source / "AGENTS.md", instructions, newline, bom=bom)
    return source


class InstallerTests(unittest.TestCase):
    def test_posix_managed_block_handles_newlines_and_bom_idempotently(self) -> None:
        shell = shutil.which("sh")
        if not shell:
            self.skipTest("a POSIX shell is unavailable")

        cases = [
            ("LF-to-LF", "\n", "\n", False, False),
            ("LF-to-CRLF", "\n", "\r\n", False, False),
            ("CRLF-to-LF", "\r\n", "\n", False, False),
            ("CRLF-to-CRLF", "\r\n", "\r\n", False, False),
            ("BOM-LF-to-CRLF", "\n", "\r\n", True, False),
            ("CRLF-to-BOM-LF", "\r\n", "\n", False, True),
            ("BOM-CRLF-to-BOM-CRLF", "\r\n", "\r\n", True, True),
        ]
        old_block = (
            f"{MANAGED_BLOCK_BEGIN}\n"
            "# Old managed workflow\n"
            f"{MANAGED_BLOCK_END}"
        )

        for name, source_newline, target_newline, source_bom, target_bom in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                fixture = Path(tmp)
                source = make_posix_source(fixture, source_newline, bom=source_bom)
                target = fixture / "target"
                target.mkdir()
                agents = target / "AGENTS.md"
                target_text = (
                    f"# User instructions\nKeep this before.\n{old_block}\n"
                    "Keep this after.\n"
                )
                write_with_newlines(agents, target_text, target_newline, bom=target_bom)

                command = [shell, str(source / "setup.sh")]
                first = run_installer_with_answers(command, target, "\nn\nn\n\n")
                updated = agents.read_bytes()
                decoded = updated.decode("utf-8-sig").replace("\r\n", "\n")
                self.assertIn("Keep this before.", decoded)
                self.assertIn("Keep this after.", decoded)
                self.assertNotIn("Old managed workflow", decoded)
                self.assertEqual(decoded.count(MANAGED_BLOCK_BEGIN), 1)
                self.assertEqual(decoded.count(MANAGED_BLOCK_END), 1)
                self.assertEqual(updated.startswith(UTF8_BOM), target_bom)
                self.assertEqual(updated.count(UTF8_BOM), int(target_bom))
                self.assertIn(
                    f"{MANAGED_BLOCK_BEGIN}\n# Codex Pro workflow", decoded
                )
                self.assertIn("Updated managed workflow block", first.stdout)

                second = run_installer_with_answers(command, target, "\nn\nn\n\n")
                self.assertEqual(agents.read_bytes(), updated)
                self.assertIn("managed workflow block already current", second.stdout)

    def test_posix_invalid_source_block_fails_closed(self) -> None:
        shell = shutil.which("sh")
        if not shell:
            self.skipTest("a POSIX shell is unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp)
            source = fixture / "source"
            source.mkdir()
            shutil.copy2(POSIX_SETUP, source / "setup.sh")
            (source / "AGENTS.md").write_text(
                f"{MANAGED_BLOCK_BEGIN}\n# Missing end marker\n", encoding="utf-8"
            )
            target = fixture / "target"
            target.mkdir()
            agents = target / "AGENTS.md"
            original = (
                f"# User\n{MANAGED_BLOCK_BEGIN}\n# Old\n{MANAGED_BLOCK_END}\n"
            ).encode("utf-8")
            agents.write_bytes(original)

            result = invoke_installer(
                [shell, str(source / "setup.sh")], target, "\nn\nn\n\n"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one valid managed workflow block", result.stderr)
            self.assertEqual(agents.read_bytes(), original)

    def test_first_install_recursively_installs_new_roles_and_managed_block(self) -> None:
        installers = available_installers()
        if not installers:
            self.skipTest("no supported installer runtime is available")

        for installer_name, command in installers:
            with self.subTest(installer=installer_name), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp)
                run_installer_with_answers(command, target, "\n\n\n\n")

                self.assertTrue((target / ".codex" / "agents" / "auditor.toml").is_file())
                self.assertTrue(
                    (target / ".codex" / "agents" / "reviewer_high.toml").is_file()
                )
                agents_text = (target / "AGENTS.md").read_text(encoding="utf-8")
                self.assertEqual(agents_text.count(MANAGED_BLOCK_BEGIN), 1)
                self.assertEqual(agents_text.count(MANAGED_BLOCK_END), 1)

    def test_managed_block_install_update_idempotence_and_content_preservation(self) -> None:
        installers = available_installers()
        if not installers:
            self.skipTest("no supported installer runtime is available")

        old_block = (
            f"{MANAGED_BLOCK_BEGIN}\n"
            "# Old managed workflow\n"
            f"{MANAGED_BLOCK_END}"
        )
        for installer_name, command in installers:
            with self.subTest(installer=installer_name), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp)
                agents = target / "AGENTS.md"
                agents.write_text(
                    f"# User instructions\n\nKeep this before.\n\n{old_block}\n\nKeep this after.\n",
                    encoding="utf-8",
                )

                first = run_installer_with_answers(command, target, "\nn\nn\n\n")
                updated = agents.read_text(encoding="utf-8")
                self.assertIn("Keep this before.", updated)
                self.assertIn("Keep this after.", updated)
                self.assertNotIn("Old managed workflow", updated)
                self.assertEqual(updated.count(MANAGED_BLOCK_BEGIN), 1)
                self.assertEqual(updated.count(MANAGED_BLOCK_END), 1)
                self.assertIn("Updated managed workflow block", first.stdout)

                second = run_installer_with_answers(command, target, "\nn\nn\n\n")
                self.assertEqual(agents.read_text(encoding="utf-8"), updated)
                self.assertIn("managed workflow block already current", second.stdout)

    def test_unmarked_legacy_workflow_is_preserved_with_warning(self) -> None:
        installers = available_installers()
        if not installers:
            self.skipTest("no supported installer runtime is available")

        legacy = "# Existing rules\nUse astra-orchestrator with Sol root.\n"
        for installer_name, command in installers:
            with self.subTest(installer=installer_name), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp)
                agents = target / "AGENTS.md"
                agents.write_text(legacy, encoding="utf-8")

                result = run_installer_with_answers(command, target, "\nn\nn\n\n")
                updated = agents.read_text(encoding="utf-8")
                self.assertIn(legacy.strip(), updated)
                self.assertEqual(updated.count(MANAGED_BLOCK_BEGIN), 1)
                self.assertIn("legacy unmarked orchestrator instructions", result.stderr)

    def test_legacy_cleanup_file_lists_match(self) -> None:
        powershell = POWERSHELL_SETUP.read_text(encoding="utf-8")
        posix = POSIX_SETUP.read_text(encoding="utf-8")

        powershell_block = re.search(
            r"\$legacyNames\s*=\s*@\((.*?)\n\s*\)", powershell, re.DOTALL
        )
        posix_block = re.search(
            r"for name in \\\n(.*?)\n\s*do", posix, re.DOTALL
        )
        self.assertIsNotNone(powershell_block)
        self.assertIsNotNone(posix_block)

        powershell_names = set(re.findall(r"'([^']+)'", powershell_block.group(1)))
        posix_names = set(re.findall(r"^\s*([\w.-]+)\s*\\?$", posix_block.group(1), re.MULTILINE))
        self.assertEqual(LEGACY_NAMES, powershell_names)
        self.assertEqual(LEGACY_NAMES, posix_names)

    def test_installer_syntax(self) -> None:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell:
            parser = (
                "$tokens = $null; $errors = $null; "
                "[System.Management.Automation.Language.Parser]::ParseFile("
                "$env:INSTALLER_UNDER_TEST, [ref]$tokens, [ref]$errors) | Out-Null; "
                "if ($errors.Count) { $errors | ForEach-Object { "
                "[Console]::Error.WriteLine($_) }; exit 1 }"
            )
            result = subprocess.run(
                [powershell, "-NoProfile", "-Command", parser],
                capture_output=True,
                text=True,
                errors="replace",
                env={**os.environ, "INSTALLER_UNDER_TEST": str(POWERSHELL_SETUP)},
                timeout=15,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        shell = shutil.which("sh")
        if shell:
            result = subprocess.run(
                [shell, "-n", str(POSIX_SETUP)],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=15,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        if not powershell and not shell:
            self.skipTest("neither PowerShell nor a POSIX shell is available")

    def test_cleanup_removes_only_confirmed_legacy_files(self) -> None:
        installers = available_installers()
        if not installers:
            self.skipTest("no supported installer runtime is available")

        for installer_name, command in installers:
            with self.subTest(installer=installer_name), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp)
                codex = target / ".codex"
                codex.mkdir()
                for name in LEGACY_NAMES:
                    content = '{"model": "deepseek-flash-2"}' if name == "models.json" else "legacy"
                    (codex / name).write_text(content, encoding="utf-8")
                unrelated = codex / "ustc_chat_adapter.py.bak"
                unrelated.write_text("keep", encoding="utf-8")

                run_installer(command, target, cleanup_answer="")

                self.assertTrue(unrelated.is_file())
                for name in LEGACY_NAMES:
                    self.assertFalse((codex / name).exists(), name)

    def test_cleanup_decline_and_custom_catalog_are_preserved(self) -> None:
        installers = available_installers()
        if not installers:
            self.skipTest("no supported installer runtime is available")

        for installer_name, command in installers:
            with self.subTest(installer=installer_name, case="decline"), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp)
                codex = target / ".codex"
                codex.mkdir()
                legacy = codex / "ustc_chat_adapter.py"
                legacy.write_text("legacy", encoding="utf-8")

                run_installer(command, target, cleanup_answer="n")
                self.assertTrue(legacy.is_file())

            with self.subTest(installer=installer_name, case="custom-catalog"), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp)
                codex = target / ".codex"
                codex.mkdir()
                catalog = codex / "models.json"
                catalog.write_text('{"model": "custom-model"}', encoding="utf-8")
                legacy = codex / "ustc_chat_adapter.py"
                legacy.write_text("legacy", encoding="utf-8")

                run_installer(command, target, cleanup_answer="")
                self.assertEqual(catalog.read_text(encoding="utf-8"), '{"model": "custom-model"}')
                self.assertFalse(legacy.exists())


if __name__ == "__main__":
    unittest.main()
