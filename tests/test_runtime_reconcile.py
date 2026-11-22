import pytest
import yaml
from dotenv import dotenv_values

from projectdavid_platform import runtime_reconcile as module


def test_generate_secrets_match_core_security_contract():
    fernet = module.generate_secret("PROJECT_DAVID_CREDENTIAL_KEY")
    from cryptography.fernet import Fernet

    Fernet(fernet.encode("ascii"))
    hmac_key = module.generate_secret("PROJECT_DAVID_PROVIDER_KEY_HMAC_KEY")
    assert len(bytes.fromhex(hmac_key)) == 32
    assert len(hmac_key) == 64
    assert fernet != module.generate_secret("PROJECT_DAVID_CREDENTIAL_KEY")
    assert hmac_key != module.generate_secret("PROJECT_DAVID_PROVIDER_KEY_HMAC_KEY")


def test_reconcile_env_additive_and_idempotent(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# User config\nCUSTOM=keep-me\nHYPERBOLIC_BASE_URL=https://custom.test\n"
    )
    additions = module.reconcile_env(
        path,
        generated_names=[
            "PROJECT_DAVID_CREDENTIAL_KEY",
            "PROJECT_DAVID_PROVIDER_KEY_HMAC_KEY",
        ],
        defaults={
            "HYPERBOLIC_BASE_URL": "https://new-default.test",
            "ADDED_DEFAULT": "42",
        },
    )
    assert set(additions) == {
        "PROJECT_DAVID_CREDENTIAL_KEY",
        "PROJECT_DAVID_PROVIDER_KEY_HMAC_KEY",
        "ADDED_DEFAULT",
    }
    before = path.read_bytes()
    v = dotenv_values(path)
    assert v["HYPERBOLIC_BASE_URL"] == "https://custom.test"
    assert v["CUSTOM"] == "keep-me"
    assert v["ADDED_DEFAULT"] == "42"
    assert (
        module.reconcile_env(
            path, generated_names=list(additions)[:2], defaults={"ADDED_DEFAULT": "12"}
        )
        == ()
    )
    assert path.read_bytes() == before


@pytest.mark.parametrize("bad", ["", "invalid", "zz" * 32])
def test_hmac_invalid_secret_never_rotated(tmp_path, bad):
    path = tmp_path / ".env"
    path.write_text(f"PROJECT_DAVID_PROVIDER_KEY_HMAC_KEY={bad}\n")
    before = path.read_bytes()
    with pytest.raises(module.RuntimeReconciliationError):
        module.reconcile_env(
            path, generated_names=["PROJECT_DAVID_PROVIDER_KEY_HMAC_KEY"], defaults={}
        )
    assert path.read_bytes() == before


def test_compose_overlay_only_new_keys_without_mutating_runtime(tmp_path):
    local = tmp_path / "docker-compose.yml"
    overlay = tmp_path / ".projectdavid-reconciled.yml"
    local.write_text(
        """# hand-edited comments\nservices:\n  api:\n    image: custom-api:v1\n    environment:\n      - A=original\n      - CUSTOM=yes\n  db:\n    image: mysql:8\nvolumes:\n  existing: {}\n"""
    )
    packaged = """services:\n  api:\n    image: new-api:v2\n    environment:\n      - A=changed\n      - NEW=${NEW}\n    restart: always\n  db:\n    image: mysql:9\n  new-worker:\n    image: new-worker:v1\nvolumes:\n  existing: {}\n  new-data: {}\n"""
    original = local.read_bytes()
    assert module.reconcile_compose(
        packaged_compose=packaged, local_compose=local, overlay_path=overlay
    )
    expected = yaml.safe_load(overlay.read_text())
    assert expected == {
        "services": {
            "api": {"environment": ["NEW=${NEW}"], "restart": "always"},
            "new-worker": {"image": "new-worker:v1"},
        },
        "volumes": {"new-data": {}},
    }
    stable = overlay.read_bytes()
    assert module.reconcile_compose(
        packaged_compose=packaged, local_compose=local, overlay_path=overlay
    )
    assert overlay.read_bytes() == stable
    assert local.read_bytes() == original


def test_compose_overlay_cleans_up_when_base_has_been_upgraded(tmp_path):
    base = tmp_path / "docker-compose.yml"
    overlay = tmp_path / ".projectdavid-reconciled.yml"
    current = "services:\n  api:\n    image: current\n    environment:\n      - NEW=1\n"
    base.write_text("services:\n  api:\n    image: old\n")
    assert module.reconcile_compose(
        packaged_compose=current, local_compose=base, overlay_path=overlay
    )
    assert overlay.exists()
    base.write_text(current)
    assert not module.reconcile_compose(
        packaged_compose=current, local_compose=base, overlay_path=overlay
    )
    assert not overlay.exists()


def test_reconcile_refuses_manually_owned_overlay(tmp_path):
    local = tmp_path / "docker-compose.yml"
    overlay = tmp_path / ".projectdavid-reconciled.yml"
    local.write_text("services: {}\n")
    overlay.write_text("# My custom config\nservices: {}\n")
    with pytest.raises(module.RuntimeReconciliationError):
        module.reconcile_compose(
            packaged_compose="services:\n  api:\n    image: new\n",
            local_compose=local,
            overlay_path=overlay,
        )
