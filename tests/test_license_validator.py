"""Regression coverage for offline license validation dependencies."""

import builtins

from projectdavid_platform import license_validator


def test_missing_cryptography_fails_closed(monkeypatch):
    """An unverifiable license must not be accepted as a valid license."""
    original_import = builtins.__import__

    def import_without_cryptography(name, *args, **kwargs):
        if name.startswith("cryptography"):
            raise ImportError("blocked for test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_cryptography)

    result = license_validator.validate_license()

    assert result.status == license_validator.LicenseStatus.INVALID
    assert result.is_runnable is False
    assert "cryptography is required" in result.message
