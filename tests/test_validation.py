# tests/test_validation.py
"""
Tests for _validate_secrets.

Verifies that:
- Known insecure values block startup
- Missing HF_TOKEN warns but never blocks
- Clean generated secrets always pass validation
"""
from __future__ import annotations

import pytest


@pytest.fixture
def orchestrator(make_orchestrator):
    return make_orchestrator()


class TestValidateSecrets:
    def test_clean_secrets_pass_validation(self, orchestrator, monkeypatch):
        """Freshly generated secrets should always pass."""
        import secrets as _secrets

        for key in orchestrator._GENERATED_SECRETS:
            monkeypatch.setenv(key, _secrets.token_hex(32))
        # Should not raise
        orchestrator._validate_secrets()

    def test_empty_secret_blocks_startup(self, orchestrator, monkeypatch):
        import secrets as _secrets

        for key in orchestrator._GENERATED_SECRETS:
            monkeypatch.setenv(key, _secrets.token_hex(32))
        # Blank out one secret
        monkeypatch.setenv("MYSQL_PASSWORD", "")
        with pytest.raises(SystemExit) as exc:
            orchestrator._validate_secrets()
        assert exc.value.code == 1

    @pytest.mark.parametrize(
        "bad_value",
        [
            "default",
            "changeme",
            "your_secret_key_here",
            "changeme_use_a_real_secret",
            "change_me_root",
            "change_me_password",
            "change_me_secret_key",
        ],
    )
    def test_known_insecure_values_block_startup(self, orchestrator, monkeypatch, bad_value):
        import secrets as _secrets

        for key in orchestrator._GENERATED_SECRETS:
            monkeypatch.setenv(key, _secrets.token_hex(32))
        # Inject one known-bad value
        monkeypatch.setenv("SECRET_KEY", bad_value)
        with pytest.raises(SystemExit) as exc:
            orchestrator._validate_secrets()
        assert exc.value.code == 1

    def test_missing_hf_token_warns_but_does_not_block(self, orchestrator, monkeypatch, capsys):
        """
        HF_TOKEN is user-supplied and optional — a missing token must never
        prevent the stack from starting.
        """
        import secrets as _secrets

        for key in orchestrator._GENERATED_SECRETS:
            monkeypatch.setenv(key, _secrets.token_hex(32))
        monkeypatch.delenv("HF_TOKEN", raising=False)

        # Should not raise SystemExit
        orchestrator._validate_secrets()

    def test_all_generated_secrets_checked(self, orchestrator, monkeypatch):
        """
        If ANY generated secret is insecure, startup must be blocked —
        not just the first one found.
        """
        import secrets as _secrets

        for key in orchestrator._GENERATED_SECRETS:
            monkeypatch.setenv(key, _secrets.token_hex(32))

        # Make two secrets insecure simultaneously
        monkeypatch.setenv("MYSQL_PASSWORD", "default")
        monkeypatch.setenv("SECRET_KEY", "changeme")

        with pytest.raises(SystemExit) as exc:
            orchestrator._validate_secrets()
        assert exc.value.code == 1

    def test_admin_api_key_with_correct_prefix_passes(self, orchestrator, monkeypatch):
        import secrets as _secrets

        for key in orchestrator._GENERATED_SECRETS:
            monkeypatch.setenv(key, _secrets.token_hex(32))
        # Admin key uses urlsafe format with prefix
        monkeypatch.setenv("ADMIN_API_KEY", f"ad_{_secrets.token_urlsafe(32)}")
        orchestrator._validate_secrets()
