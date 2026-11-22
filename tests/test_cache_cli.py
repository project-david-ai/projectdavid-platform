from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from projectdavid_platform.start_orchestration import Orchestrator, app

runner = CliRunner()


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    hf_cache = tmp_path / "hf-cache"
    hub = hf_cache / "hub"
    hub.mkdir(parents=True)

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "HF_TOKEN=",
                f"SHARED_PATH={tmp_path / 'shared_data'}",
                f"HF_CACHE_PATH={hf_cache}",
            ]
        ),
        encoding="utf-8",
    )

    (tmp_path / "docker-compose.yml").write_text(
        "services: {}\n",
        encoding="utf-8",
    )

    return {
        "runtime": tmp_path,
        "hf_cache": hf_cache,
        "hub": hub,
    }


def extract_json_payload(output: str) -> dict:
    for line in reversed(output.splitlines()):
        candidate = line.strip()

        if not candidate.startswith("{"):
            continue

        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if isinstance(payload, dict) and "status" in payload:
            return payload

    raise AssertionError("CLI output did not contain a JSON payload")


def test_cache_list_json_returns_cached_huggingface_models(
    runtime,
    monkeypatch,
):
    (runtime["hub"] / "models--Qwen--Qwen2.5-VL-3B-Instruct-AWQ").mkdir()
    (runtime["hub"] / "models--meta-llama--Llama-3.2-11B-Vision-Instruct-GPTQ").mkdir()

    monkeypatch.setattr(
        Orchestrator,
        "_is_container_running",
        lambda self, node: False,
    )

    result = runner.invoke(
        app,
        [
            "cache",
            "--list",
            "--json",
        ],
    )

    assert result.exit_code == 0

    payload = extract_json_payload(result.stdout)

    assert payload == {
        "status": "ok",
        "node": "inference_worker",
        "count": 2,
        "models": [
            {
                "hf_model_id": ("meta-llama/" "Llama-3.2-11B-Vision-Instruct-GPTQ"),
            },
            {
                "hf_model_id": ("Qwen/" "Qwen2.5-VL-3B-Instruct-AWQ"),
            },
        ],
    }


def test_cache_list_json_returns_empty_model_list(
    runtime,
    monkeypatch,
):
    monkeypatch.setattr(
        Orchestrator,
        "_is_container_running",
        lambda self, node: False,
    )

    result = runner.invoke(
        app,
        [
            "cache",
            "--list",
            "--json",
        ],
    )

    assert result.exit_code == 0

    payload = extract_json_payload(result.stdout)

    assert payload == {
        "status": "ok",
        "node": "inference_worker",
        "count": 0,
        "models": [],
    }
