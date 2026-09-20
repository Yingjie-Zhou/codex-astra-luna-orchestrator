from __future__ import annotations

import copy
import re
import tomllib
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROFILES_ROOT = REPOSITORY_ROOT / "profiles"
PROFILE_NAMES = ("pro", "pro-max-2-subagents")
LUNA_HIGH_ROLES = ("explorer", "tester", "researcher")
MANAGED_BLOCK_BEGIN = "<!-- BEGIN CODEX PRO WORKFLOW -->"
MANAGED_BLOCK_END = "<!-- END CODEX PRO WORKFLOW -->"


def load_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


class ProfileConfigTests(unittest.TestCase):
    def test_only_pro_profiles_remain(self) -> None:
        self.assertEqual(
            set(PROFILE_NAMES),
            {path.name for path in PROFILES_ROOT.iterdir() if path.is_dir()},
        )

    def test_root_configs_use_sol_and_luna_high_defaults(self) -> None:
        for name in PROFILE_NAMES:
            with self.subTest(profile=name):
                config = load_toml(PROFILES_ROOT / name / "codex" / "config.toml")
                self.assertEqual(config["model"], "gpt-5.6-sol")
                self.assertEqual(config["model_reasoning_effort"], "high")
                self.assertNotIn("model_provider", config)
                self.assertNotIn("model_catalog_json", config)
                self.assertNotIn("model_providers", config)

                agents = config["agents"]
                self.assertEqual(agents["default_subagent_model"], "gpt-5.6-luna")
                self.assertEqual(agents["default_subagent_reasoning_effort"], "high")

    def test_luna_high_roles_are_explicit(self) -> None:
        for profile in PROFILE_NAMES:
            for role in LUNA_HIGH_ROLES:
                with self.subTest(profile=profile, role=role):
                    config = load_toml(
                        PROFILES_ROOT / profile / "codex" / "agents" / f"{role}.toml"
                    )
                    self.assertEqual(config["model"], "gpt-5.6-luna")
                    self.assertEqual(config["model_provider"], "openai")
                    self.assertEqual(config["model_reasoning_effort"], "high")

    def test_worker_uses_luna_max(self) -> None:
        for profile in PROFILE_NAMES:
            with self.subTest(profile=profile):
                config = load_toml(
                    PROFILES_ROOT / profile / "codex" / "agents" / "worker.toml"
                )
                self.assertEqual(config["model"], "gpt-5.6-luna")
                self.assertEqual(config["model_provider"], "openai")
                self.assertEqual(config["model_reasoning_effort"], "max")

    def test_auditor_is_read_only_luna_max_with_behavior_gate(self) -> None:
        classifications = {
            "CONFIRMED",
            "PARTIALLY_CONFIRMED",
            "CONTRADICTED",
            "UNKNOWN",
        }
        for profile in PROFILE_NAMES:
            with self.subTest(profile=profile):
                config = load_toml(
                    PROFILES_ROOT / profile / "codex" / "agents" / "auditor.toml"
                )
                self.assertEqual(config["model"], "gpt-5.6-luna")
                self.assertEqual(config["model_provider"], "openai")
                self.assertEqual(config["model_reasoning_effort"], "max")
                self.assertEqual(config["sandbox_mode"], "read-only")
                instructions = config["developer_instructions"]
                for classification in classifications:
                    self.assertIn(classification, instructions)
                self.assertIn("material semantic conflict", instructions)
                self.assertIn("Implementation must not begin", instructions)
                self.assertIn("Behavior contract", instructions)

    def test_solver_and_reviewer_are_explicit(self) -> None:
        expected = {
            "solver": ("gpt-5.6-sol", "high", "workspace-write"),
            "reviewer": ("gpt-6-astra", "low", "read-only"),
            "reviewer_high": ("gpt-6-astra", "high", "read-only"),
        }
        for profile in PROFILE_NAMES:
            for role, values in expected.items():
                with self.subTest(profile=profile, role=role):
                    config = load_toml(
                        PROFILES_ROOT / profile / "codex" / "agents" / f"{role}.toml"
                    )
                    self.assertEqual(config["model_provider"], "openai")
                    self.assertEqual(
                        (
                            config["model"],
                            config["model_reasoning_effort"],
                            config["sandbox_mode"],
                        ),
                        values,
                    )

    def test_max_two_profile_only_changes_concurrency(self) -> None:
        regular = load_toml(PROFILES_ROOT / "pro" / "codex" / "config.toml")
        limited = load_toml(
            PROFILES_ROOT / "pro-max-2-subagents" / "codex" / "config.toml"
        )
        self.assertEqual(regular["agents"]["max_concurrent_threads_per_session"], 4)
        self.assertEqual(limited["agents"]["max_concurrent_threads_per_session"], 2)

        normalized = copy.deepcopy(regular)
        normalized["agents"]["max_concurrent_threads_per_session"] = 2
        self.assertEqual(normalized, limited)

        regular_agents = PROFILES_ROOT / "pro" / "codex" / "agents"
        limited_agents = PROFILES_ROOT / "pro-max-2-subagents" / "codex" / "agents"
        self.assertEqual(
            {path.name for path in regular_agents.glob("*.toml")},
            {path.name for path in limited_agents.glob("*.toml")},
        )
        for role_file in regular_agents.glob("*.toml"):
            with self.subTest(role=role_file.stem):
                self.assertEqual(
                    load_toml(role_file), load_toml(limited_agents / role_file.name)
                )

        regular_skill = (
            PROFILES_ROOT / "pro" / "agents" / "skills" / "astra-orchestrator" / "SKILL.md"
        )
        limited_skill = (
            PROFILES_ROOT
            / "pro-max-2-subagents"
            / "agents"
            / "skills"
            / "astra-orchestrator"
            / "SKILL.md"
        )
        self.assertEqual(
            regular_skill.read_text(encoding="utf-8"),
            limited_skill.read_text(encoding="utf-8"),
        )

    def test_managed_agents_block_is_well_formed(self) -> None:
        instructions = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(instructions.count(MANAGED_BLOCK_BEGIN), 1)
        self.assertEqual(instructions.count(MANAGED_BLOCK_END), 1)
        self.assertLess(
            instructions.index(MANAGED_BLOCK_BEGIN), instructions.index(MANAGED_BLOCK_END)
        )
        self.assertIn("R0", instructions)
        self.assertIn("R3", instructions)
        self.assertIn("reviewer_high", instructions)
        self.assertIn("manual acceptance", instructions)

    def test_profiles_have_no_deepseek_assets_or_secrets(self) -> None:
        forbidden_names = {
            "models.json",
            "local_deepseek_runner.py",
            "run-deepseek-role.ps1",
            "start-ustc-adapter.ps1",
            "start-ustc-adapter.sh",
            "ustc_chat_adapter.py",
        }
        for profile in PROFILE_NAMES:
            codex = PROFILES_ROOT / profile / "codex"
            self.assertTrue(forbidden_names.isdisjoint({p.name for p in codex.rglob("*")}))
            for path in codex.rglob("*"):
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8")
                with self.subTest(path=path):
                    self.assertNotRegex(text.lower(), r"deepseek|ustc")
                    self.assertNotIn("experimental_bearer_token", text)
                    self.assertIsNone(re.search(r"\bsk-[A-Za-z0-9]", text))


if __name__ == "__main__":
    unittest.main()
