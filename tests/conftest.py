# tests/conftest.py
"""
Shared fixtures for the projectdavid-platform test suite.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Minimal args namespace — mirrors what the CLI assembles before passing
# to Orchestrator.__init__
# ---------------------------------------------------------------------------
@pytest.fixture
def base_args():
    return SimpleNamespace(
        mode="up",
        gpu=False,
        services=[],
        exclude=[],
        down=False,
        clear_volumes=False,
        force_recreate=False,
        attached=False,
        build_before_up=False,
        no_cache=False,
        parallel=False,
        nuke=False,
        follow=False,
        tail=None,
        timestamps=False,
        no_log_prefix=False,
        verbose=False,
    )


# ---------------------------------------------------------------------------
# Temporary .env file — written to a tmp directory, never touches the real one
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    """
    Redirects _ENV_FILE to a temp directory so tests never touch the real .env.
    Returns the Path to the temp .env file (may not exist yet).
    """
    env_file = tmp_path / ".env"
    monkeypatch.chdir(tmp_path)
    return env_file


# ---------------------------------------------------------------------------
# Minimal compose config — returned by _load_compose_config so tests don't
# need a real docker-compose.yml on disk
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_compose_config():
    return {
        "services": {
            "db": {
                "image": "mysql:8.0",
                "ports": ["3307:3306"],
                "environment": {
                    "MYSQL_ROOT_PASSWORD": "${MYSQL_ROOT_PASSWORD}",
                    "MYSQL_DATABASE": "entities_db",
                    "MYSQL_USER": "api_user",
                    "MYSQL_PASSWORD": "${MYSQL_PASSWORD}",
                },
            },
            "api": {"image": "thanosprime/entities-api-api:latest"},
            "sandbox": {"image": "thanosprime/entities-api-sandbox:latest"},
            "redis": {"image": "redis:7"},
            "qdrant": {"image": "qdrant/qdrant:latest"},
            "searxng": {"image": "searxng/searxng:latest"},
            "samba": {"image": "dperson/samba"},
        }
    }


# ---------------------------------------------------------------------------
# Orchestrator factory — builds a real Orchestrator with mocked Docker and
# compose loading so unit tests never shell out
# ---------------------------------------------------------------------------
@pytest.fixture
def make_orchestrator(base_args, tmp_env, mock_compose_config, monkeypatch):
    """
    Returns a factory function: call make_orchestrator() to get an Orchestrator
    instance with Docker and file I/O mocked out.
    """

    def _factory(args=None):
        from projectdavid_platform.start_orchestration import Orchestrator

        _args = args or base_args

        # Prevent real compose file loading
        monkeypatch.setattr(Orchestrator, "_load_compose_config", lambda self: mock_compose_config)
        # Prevent real .env generation side effects during __init__
        monkeypatch.setattr(Orchestrator, "_check_for_required_env_file", lambda self: None)
        monkeypatch.setattr(Orchestrator, "_configure_shared_path", lambda self: None)
        monkeypatch.setattr(Orchestrator, "_configure_hf_cache_path", lambda self: None)
        monkeypatch.setattr(Orchestrator, "_ensure_dockerignore", lambda self: None)

        o = Orchestrator(_args)
        o.compose_config = mock_compose_config
        return o

    return _factory
