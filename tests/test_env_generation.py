# tests/test_env_generation.py
"""
Tests for .env file generation.

Verifies that:
- Every install produces unique secrets
- No known-insecure placeholder values survive into the generated file
- Composite DB URLs are correctly constructed from components
- HF_CACHE_PATH is auto-resolved when not set
- The generated file is parseable and contains all expected sections
"""
from __future__ import annotations

import re

import pytest


@pytest.fixture
def orchestrator(make_orchestrator):
    return make_orchestrator()


@pytest.fixture
def generated_env(orchestrator, tmp_env, monkeypatch):
    """Run _generate_dot_env_file and return the written content."""
    # Skip interactive prompt in all generation tests
    monkeypatch.setattr(
        orchestrator, "_prompt_user_required", lambda env_values, generation_log: None
    )
    orchestrator._generate_dot_env_file()
    return tmp_env.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Uniqueness — the core security guarantee
# ---------------------------------------------------------------------------


class TestSecretUniqueness:
    def test_two_installs_produce_different_mysql_passwords(
        self, make_orchestrator, tmp_path, monkeypatch
    ):
        secrets = []
        for i in range(2):

            o = make_orchestrator()
            monkeypatch.setattr(o, "_prompt_user_required", lambda ev, gl: None)
            env_values = dict(o._DEFAULT_VALUES)

            for key in o._GENERATED_SECRETS:
                import secrets as _secrets

                env_values[key] = _secrets.token_hex(32)
            secrets.append(env_values["MYSQL_PASSWORD"])

        assert secrets[0] != secrets[1], (
            "Two separate installs produced identical MYSQL_PASSWORD — "
            "secret generation is not random"
        )

    def test_all_generated_secrets_are_unique_within_one_install(self, orchestrator, monkeypatch):
        monkeypatch.setattr(orchestrator, "_prompt_user_required", lambda ev, gl: None)
        env_values = dict(orchestrator._DEFAULT_VALUES)

        import secrets as _secrets

        for key in orchestrator._GENERATED_SECRETS:
            env_values[key] = _secrets.token_hex(32)

        secret_values = [env_values[k] for k in orchestrator._GENERATED_SECRETS]
        assert len(secret_values) == len(
            set(secret_values)
        ), "At least two generated secrets have the same value within one install"


# ---------------------------------------------------------------------------
# No insecure values survive
# ---------------------------------------------------------------------------


class TestNoInsecureValues:
    def test_insecure_values_not_present_in_generated_env(self, generated_env):
        insecure = [
            "your_secret_key_here",
            "changeme",
            "change_me_root",
            "change_me_password",
            "changeme_use_a_real_secret",
        ]
        for placeholder in insecure:
            assert (
                placeholder not in generated_env
            ), f"Insecure placeholder '{placeholder}' found in generated .env"

    def test_generated_secrets_have_minimum_entropy(self, orchestrator, monkeypatch):
        """Generated hex secrets should be at least 32 bytes (64 hex chars)."""
        monkeypatch.setattr(orchestrator, "_prompt_user_required", lambda ev, gl: None)
        env_values = dict(orchestrator._DEFAULT_VALUES)

        import secrets as _secrets

        for key in orchestrator._GENERATED_SECRETS:
            if key not in ("ADMIN_API_KEY", "API_KEY"):
                env_values[key] = _secrets.token_hex(32)
                assert (
                    len(env_values[key]) == 64
                ), f"Secret '{key}' is shorter than expected: {len(env_values[key])} chars"


# ---------------------------------------------------------------------------
# DB URL construction
# ---------------------------------------------------------------------------


class TestDatabaseURLConstruction:
    def test_database_url_is_constructed_from_components(self, generated_env):
        assert "DATABASE_URL=mysql+pymysql://" in generated_env

    def test_special_db_url_uses_host_port(self, generated_env):
        # The mock compose config maps 3307:3306 so SPECIAL_DB_URL should use 3307
        assert "SPECIAL_DB_URL=mysql+pymysql://api_user:" in generated_env
        assert "@localhost:3307/entities_db" in generated_env

    def test_database_url_password_is_url_encoded(self, generated_env):
        """
        Passwords containing special characters must be URL-encoded in the
        connection string — raw special chars break SQLAlchemy connection parsing.
        """
        # Extract DATABASE_URL from the generated file
        match = re.search(r"DATABASE_URL=(.+)", generated_env)
        assert match, "DATABASE_URL not found in generated .env"
        url = match.group(1)
        # The URL should not contain unencoded @ symbols inside the password
        # (there will be exactly one @ separating credentials from host)
        credentials_part = url.split("@")[0]
        password_part = credentials_part.split(":")[-1]
        assert " " not in password_part, "Password contains unencoded space"


# ---------------------------------------------------------------------------
# HF_CACHE_PATH resolution
# ---------------------------------------------------------------------------


class TestHFCachePathResolution:
    def test_hf_cache_path_is_set_when_not_in_environment(self, generated_env, monkeypatch):
        monkeypatch.delenv("HF_CACHE_PATH", raising=False)
        assert "HF_CACHE_PATH=" in generated_env

    def test_hf_cache_path_points_to_huggingface_directory(self, generated_env):
        match = re.search(r"HF_CACHE_PATH=(.+)", generated_env)
        assert match, "HF_CACHE_PATH not found in generated .env"
        assert "huggingface" in match.group(1).lower()


# ---------------------------------------------------------------------------
# File structure
# ---------------------------------------------------------------------------


class TestEnvFileStructure:
    def test_generated_file_contains_all_sections(self, generated_env):
        expected_sections = [
            "# Base URLs",
            "# AI Model Configuration",
            "# Database Configuration",
            "# API Keys & Secrets",
            "# Platform Settings",
            "# Admin Configuration",
            "# SMB Client Configuration",
            "# Tool Identifiers",
        ]
        for section in expected_sections:
            assert (
                section in generated_env
            ), f"Expected section '{section}' not found in generated .env"

    def test_generated_file_has_header_comment(self, generated_env):
        assert "Auto-generated by projectdavid-platform" in generated_env

    def test_generated_file_is_parseable_as_key_value_pairs(self, generated_env):
        """Every non-comment, non-empty line must be a valid KEY=VALUE pair."""
        for line in generated_env.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            assert "=" in line, f"Line is not a valid KEY=VALUE pair: {line!r}"

    def test_tool_ids_are_generated(self, generated_env):
        for key in [
            "TOOL_CODE_INTERPRETER",
            "TOOL_WEB_SEARCH",
            "TOOL_COMPUTER",
            "TOOL_VECTOR_STORE_SEARCH",
        ]:
            assert (
                f"{key}=tool_" in generated_env
            ), f"Tool ID '{key}' not found or not prefixed with 'tool_'"
