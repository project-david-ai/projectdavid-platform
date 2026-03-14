# tests/test_configure.py
"""
Tests for in-place .env patching via the configure command.

Verifies that:
- Existing keys are updated without touching other values
- New keys are appended cleanly
- Generated secrets are never modified by configure
- Rotation categories trigger correct warnings
"""
from __future__ import annotations

import re

import pytest
from typer.testing import CliRunner

from projectdavid_platform.start_orchestration import (
    app,
)

runner = CliRunner()


@pytest.fixture
def populated_env(tmp_path, monkeypatch):
    """
    Write a realistic .env to tmp_path and chdir there.
    Returns the Path to the .env file.
    """
    import secrets as _secrets

    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / ".env"

    lines = [
        "# Test .env",
        f"MYSQL_PASSWORD={_secrets.token_hex(32)}",
        f"SECRET_KEY={_secrets.token_hex(32)}",
        f"ADMIN_API_KEY=ad_{_secrets.token_urlsafe(32)}",
        "HF_TOKEN=",
        "VLLM_MODEL=Qwen/Qwen2.5-VL-3B-Instruct",
        "LOG_LEVEL=INFO",
    ]
    env_path.write_text("\n".join(lines), encoding="utf-8")
    return env_path


class TestConfigureUpdateExistingKey:
    def test_updates_existing_key_value(self, populated_env):
        result = runner.invoke(app, ["configure", "--set", "HF_TOKEN=hf_abc123"])
        assert result.exit_code == 0
        content = populated_env.read_text()
        assert "HF_TOKEN=hf_abc123" in content

    def test_does_not_duplicate_key(self, populated_env):
        runner.invoke(app, ["configure", "--set", "HF_TOKEN=hf_abc123"])
        content = populated_env.read_text()
        matches = re.findall(r"^HF_TOKEN=", content, re.MULTILINE)
        assert len(matches) == 1, "Key was duplicated instead of updated"

    def test_does_not_touch_other_keys(self, populated_env):
        original = populated_env.read_text()
        original_mysql = re.search(r"MYSQL_PASSWORD=(.+)", original).group(1)

        runner.invoke(app, ["configure", "--set", "HF_TOKEN=hf_abc123"])

        updated = populated_env.read_text()
        updated_mysql = re.search(r"MYSQL_PASSWORD=(.+)", updated).group(1)
        assert (
            original_mysql == updated_mysql
        ), "configure modified MYSQL_PASSWORD when it should not have"

    def test_updates_multiple_keys_in_one_call(self, populated_env):
        runner.invoke(
            app,
            [
                "configure",
                "--set",
                "HF_TOKEN=hf_abc123",
                "--set",
                "VLLM_MODEL=Qwen/Qwen2.5-VL-7B-Instruct",
            ],
        )
        content = populated_env.read_text()
        assert "HF_TOKEN=hf_abc123" in content
        assert "VLLM_MODEL=Qwen/Qwen2.5-VL-7B-Instruct" in content


class TestConfigureAppendNewKey:
    def test_appends_key_not_previously_in_env(self, populated_env):
        runner.invoke(app, ["configure", "--set", "NEW_CUSTOM_VAR=hello"])
        content = populated_env.read_text()
        assert "NEW_CUSTOM_VAR=hello" in content

    def test_appended_key_has_marker_comment(self, populated_env):
        runner.invoke(app, ["configure", "--set", "NEW_CUSTOM_VAR=hello"])
        content = populated_env.read_text()
        assert "# Added by pdavid configure" in content


class TestConfigureValueQuoting:
    def test_values_with_spaces_are_quoted(self, populated_env):
        runner.invoke(app, ["configure", "--set", "LOG_LEVEL=very verbose"])
        content = populated_env.read_text()
        assert 'LOG_LEVEL="very verbose"' in content

    def test_simple_values_are_not_quoted(self, populated_env):
        runner.invoke(app, ["configure", "--set", "LOG_LEVEL=DEBUG"])
        content = populated_env.read_text()
        assert "LOG_LEVEL=DEBUG" in content
        assert 'LOG_LEVEL="DEBUG"' not in content


class TestConfigureRotationWarnings:
    def test_dangerous_rotation_prints_warning(self, populated_env):
        result = runner.invoke(app, ["configure", "--set", "MYSQL_PASSWORD=newpassword"])
        assert "WARNING" in result.output

    def test_requires_down_prints_restart_note(self, populated_env):
        result = runner.invoke(app, ["configure", "--set", "SECRET_KEY=newsecret"])
        assert "restart" in result.output.lower() or "down" in result.output.lower()

    def test_safe_key_prints_force_recreate_hint(self, populated_env):
        result = runner.invoke(app, ["configure", "--set", "HF_TOKEN=hf_abc123"])
        assert "force-recreate" in result.output

    def test_no_update_exits_cleanly(self, populated_env):
        result = runner.invoke(app, ["configure"])
        assert result.exit_code == 0
        assert "Nothing to update" in result.output


class TestConfigureInvalidInput:
    def test_malformed_set_argument_exits_with_error(self, populated_env):
        result = runner.invoke(app, ["configure", "--set", "NOEQUALSSIGN"])
        assert result.exit_code != 0

    def test_missing_env_file_exits_with_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # No .env file present
        result = runner.invoke(app, ["configure", "--set", "HF_TOKEN=hf_abc123"])
        assert result.exit_code != 0
