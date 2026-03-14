# tests/test_path_resolution.py
"""
Tests for _resolve_compose_file.

Verifies that:
- Local files take priority over bundled package data
- Bundled package data is found when no local file exists
- A clear warning is logged when neither is found
- Both base and GPU compose files resolve correctly
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from projectdavid_platform.start_orchestration import (
    BASE_COMPOSE_FILE,
    GPU_COMPOSE_FILE,
    _resolve_compose_file,
)


class TestLocalFilePriority:
    def test_local_file_wins_over_package_data(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        local = tmp_path / BASE_COMPOSE_FILE
        local.write_text("# local compose", encoding="utf-8")

        result = _resolve_compose_file(BASE_COMPOSE_FILE)
        assert result == str(local)

    def test_local_gpu_file_wins_over_package_data(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        local = tmp_path / GPU_COMPOSE_FILE
        local.write_text("# local gpu compose", encoding="utf-8")

        result = _resolve_compose_file(GPU_COMPOSE_FILE)
        assert result == str(local)

    def test_local_file_path_is_absolute(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        local = tmp_path / BASE_COMPOSE_FILE
        local.write_text("# local", encoding="utf-8")

        result = _resolve_compose_file(BASE_COMPOSE_FILE)
        assert Path(result).is_absolute()


class TestPackageDataFallback:
    def test_falls_back_to_package_data_when_no_local_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # No local file — should try importlib.resources
        fake_path = tmp_path / "bundled" / BASE_COMPOSE_FILE
        fake_path.parent.mkdir()
        fake_path.write_text("# bundled", encoding="utf-8")

        mock_resource = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=fake_path)
        mock_context.__exit__ = MagicMock(return_value=False)

        with patch("importlib.resources.files") as mock_files:
            mock_files.return_value.__truediv__ = MagicMock(return_value=mock_resource)
            with patch("importlib.resources.as_file", return_value=mock_context):
                result = _resolve_compose_file(BASE_COMPOSE_FILE)
                assert result == str(fake_path)

    def test_returns_filename_and_warns_when_neither_found(self, tmp_path, monkeypatch, caplog):
        monkeypatch.chdir(tmp_path)

        with patch("importlib.resources.files", side_effect=ModuleNotFoundError):
            result = _resolve_compose_file(BASE_COMPOSE_FILE)

        # Falls back to the bare filename
        assert result == BASE_COMPOSE_FILE
        # Warning should have been logged
        assert any(
            "not found" in r.message.lower() or "reinstall" in r.message.lower()
            for r in caplog.records
        )


class TestBothComposeFilesResolvable:
    def test_base_compose_resolves(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        local = tmp_path / BASE_COMPOSE_FILE
        local.write_text("services:", encoding="utf-8")
        assert _resolve_compose_file(BASE_COMPOSE_FILE) == str(local)

    def test_gpu_compose_resolves(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        local = tmp_path / GPU_COMPOSE_FILE
        local.write_text("services:", encoding="utf-8")
        assert _resolve_compose_file(GPU_COMPOSE_FILE) == str(local)
