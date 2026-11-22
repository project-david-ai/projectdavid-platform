from pathlib import Path


def test_packaged_compose_matches_canonical_root_compose():
    repo = Path(__file__).resolve().parents[1]

    canonical = (repo / "docker-compose.yml").read_bytes()

    packaged = (repo / "projectdavid_platform" / "docker-compose.yml").read_bytes()

    assert packaged == canonical


def test_packaged_compose_exposes_q_model_hub_runtime_read_only():
    repo = Path(__file__).resolve().parents[1]

    compose = (repo / "projectdavid_platform" / "docker-compose.yml").read_text(
        encoding="utf-8",
    )

    assert "MODEL_HUB_RUNTIME_ROOT=" "/opt/projectdavid/model-hub/models" in compose

    assert (
        "${MODEL_HUB_RUNTIME_PATH:-./model-hub-runtime}"
        ":/opt/projectdavid/model-hub/models:ro" in compose
    )
