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


def run_installer(command: list[str], target: Path, cleanup_answer: str) -> None:
    answers = f"{target}\n\n\ny\n{cleanup_answer}\nn\nn\n"
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        input=answers,
        text=True,
        errors="replace",
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"installer failed ({result.returncode})\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


class InstallerTests(unittest.TestCase):
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
