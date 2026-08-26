"""Regression coverage for Project David Platform licence enforcement."""

import builtins

from projectdavid_platform import license_validator, start_orchestration


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


def test_runtime_license_is_enforced_for_normal_platform(monkeypatch):
    """Ordinary Platform startup must invoke the licence validator."""
    calls = []

    monkeypatch.setattr(
        start_orchestration,
        "_FIRST_PARTY_EMBEDDED_RUNTIME",
        False,
    )
    monkeypatch.setattr(
        start_orchestration,
        "_LICENSE_AVAILABLE",
        True,
    )
    monkeypatch.setattr(
        start_orchestration,
        "enforce_license",
        lambda: calls.append("enforced"),
    )

    assert start_orchestration._enforce_runtime_license() is True
    assert calls == ["enforced"]


def test_missing_validator_blocks_normal_platform(monkeypatch, caplog):
    """Ordinary Platform startup must fail closed if its validator disappears."""
    monkeypatch.setattr(
        start_orchestration,
        "_FIRST_PARTY_EMBEDDED_RUNTIME",
        False,
    )
    monkeypatch.setattr(
        start_orchestration,
        "_LICENSE_AVAILABLE",
        False,
    )
    monkeypatch.setattr(
        start_orchestration,
        "enforce_license",
        None,
    )

    assert start_orchestration._enforce_runtime_license() is False
    assert "licence validator is unavailable" in caplog.text.lower()


def test_first_party_embedded_runtime_skips_license(monkeypatch):
    """Q's deliberately frozen runtime may start without the commercial validator."""

    def unexpected_enforcement():
        raise AssertionError("Q embedded runtime must not invoke enforce_license")

    monkeypatch.setattr(
        start_orchestration,
        "_FIRST_PARTY_EMBEDDED_RUNTIME",
        True,
    )
    monkeypatch.setattr(
        start_orchestration,
        "_LICENSE_AVAILABLE",
        False,
    )
    monkeypatch.setattr(
        start_orchestration,
        "enforce_license",
        unexpected_enforcement,
    )

    assert start_orchestration._enforce_runtime_license() is True


def test_preflight_stops_before_docker_when_license_gate_fails(monkeypatch):
    """A failed licence gate must stop startup before Docker preflight work."""
    orchestrator = start_orchestration.Orchestrator.__new__(
        start_orchestration.Orchestrator
    )
    orchestrator.log = start_orchestration.log
    orchestrator.args = type(
        "Args",
        (),
        {
            "training": False,
            "vllm": False,
            "ollama": False,
        },
    )()

    docker_calls = []

    monkeypatch.setattr(
        start_orchestration,
        "_enforce_runtime_license",
        lambda: False,
    )
    monkeypatch.setattr(
        orchestrator,
        "_has_docker",
        lambda: docker_calls.append("docker") or True,
    )

    assert orchestrator._preflight() is False
    assert docker_calls == []
