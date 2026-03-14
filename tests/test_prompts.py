# tests/test_prompts.py
"""
Tests for _prompt_user_required.

Verifies that:
- Shell environment variables are inherited without prompting
- Non-interactive environments (CI) skip all prompts silently
- Only unset variables are prompted for
- Provided values are written into env_values
- Skipped values leave env_values unchanged
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def orchestrator(make_orchestrator):
    return make_orchestrator()


class TestShellEnvironmentInheritance:
    def test_inherits_hf_token_from_shell(self, orchestrator, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "hf_from_shell")
        env_values = {}
        generation_log = {}

        with patch("typer.echo"):
            orchestrator._prompt_user_required(env_values, generation_log)

        assert env_values.get("HF_TOKEN") == "hf_from_shell"
        assert generation_log.get("HF_TOKEN") == "Inherited from shell environment"

    def test_inherited_value_skips_prompt(self, orchestrator, monkeypatch):
        monkeypatch.setenv("HF_TOKEN", "hf_from_shell")
        env_values = {}
        generation_log = {}

        # If prompt were called it would raise — patching typer.prompt to raise
        # confirms it is never called when value is inherited
        with patch("typer.prompt", side_effect=AssertionError("prompt was called")):
            with patch("typer.echo"):
                orchestrator._prompt_user_required(env_values, generation_log)

        # No assertion error means prompt was never called
        assert env_values["HF_TOKEN"] == "hf_from_shell"

    def test_partial_inheritance_only_prompts_for_missing(self, orchestrator, monkeypatch):
        """
        If some _USER_REQUIRED keys are in the environment and others are not,
        only the missing ones should be prompted for.
        """
        # Add a second user-required key for this test
        original = dict(orchestrator._USER_REQUIRED)
        orchestrator._USER_REQUIRED = {
            "HF_TOKEN": original["HF_TOKEN"],
            "ANOTHER_TOKEN": ("ANOTHER_TOKEN", "Another token", True),
        }
        monkeypatch.setenv("HF_TOKEN", "hf_from_shell")
        monkeypatch.delenv("ANOTHER_TOKEN", raising=False)

        prompted_keys = []

        def fake_prompt(label, **kwargs):
            prompted_keys.append(label)
            return ""

        with patch("sys.stdin.isatty", return_value=True):
            with patch("typer.prompt", side_effect=fake_prompt):
                with patch("typer.echo"):
                    env_values = {}
                    orchestrator._prompt_user_required(env_values, {})

        # Only ANOTHER_TOKEN should have been prompted
        assert any("ANOTHER_TOKEN" in k for k in prompted_keys)
        assert not any("HF_TOKEN" in k for k in prompted_keys)

        # Restore
        orchestrator._USER_REQUIRED = original


class TestNonInteractiveEnvironment:
    def test_skips_all_prompts_in_ci(self, orchestrator, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)

        with patch("sys.stdin.isatty", return_value=False):
            with patch("typer.prompt", side_effect=AssertionError("prompt in CI")):
                env_values = {}
                orchestrator._prompt_user_required(env_values, {})

        # HF_TOKEN should remain unset
        assert "HF_TOKEN" not in env_values or env_values.get("HF_TOKEN") == ""

    def test_logs_warning_in_ci(self, orchestrator, monkeypatch, caplog):
        monkeypatch.delenv("HF_TOKEN", raising=False)

        with patch("sys.stdin.isatty", return_value=False):
            env_values = {}
            orchestrator._prompt_user_required(env_values, {})

        assert any(
            "non-interactive" in r.message.lower() or "left blank" in r.message.lower()
            for r in caplog.records
        )


class TestInteractivePromptBehaviour:
    def test_provided_value_is_saved(self, orchestrator, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        env_values = {}
        generation_log = {}

        with patch("sys.stdin.isatty", return_value=True):
            with patch("typer.prompt", return_value="hf_user_typed"):
                with patch("typer.echo"):
                    orchestrator._prompt_user_required(env_values, generation_log)

        assert env_values.get("HF_TOKEN") == "hf_user_typed"
        assert generation_log.get("HF_TOKEN") == "Provided interactively by user"

    def test_skipped_value_leaves_env_unchanged(self, orchestrator, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        env_values = {"HF_TOKEN": ""}
        generation_log = {}

        with patch("sys.stdin.isatty", return_value=True):
            # User presses Enter — returns empty string
            with patch("typer.prompt", return_value=""):
                with patch("typer.echo"):
                    orchestrator._prompt_user_required(env_values, generation_log)

        # Value should remain empty — not set to anything
        assert env_values.get("HF_TOKEN", "") == ""
        assert generation_log.get("HF_TOKEN") != "Provided interactively by user"
