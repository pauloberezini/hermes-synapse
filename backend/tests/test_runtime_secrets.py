"""Production compose must refuse known-default secrets; local/dev must not."""
import pytest

from backend.runtime_secrets import enforce_runtime_secrets, validate_runtime_secrets

_OK = {
    "ENV": "production",
    "JWT_SECRET": "a" * 32,
    "POSTGRES_PASSWORD": "not-postgres-1",
    "DATABASE_URL": "postgresql://hermes:not-postgres-1@db:5432/hermes",
    "QDRANT_API_KEY": "qdrant-key-16ch+",
}


def test_dev_and_unset_env_are_not_checked():
    assert validate_runtime_secrets({}) == []
    assert validate_runtime_secrets({"ENV": "development", "JWT_SECRET": ""}) == []
    assert validate_runtime_secrets({"ENV": "test"}) == []


def test_production_accepts_strong_secrets():
    assert validate_runtime_secrets(_OK) == []


@pytest.mark.parametrize(
    "override,fragment",
    [
        ({"JWT_SECRET": ""}, "JWT_SECRET"),
        ({"JWT_SECRET": "secret"}, "JWT_SECRET"),
        ({"JWT_SECRET": "short"}, "JWT_SECRET"),
        ({"POSTGRES_PASSWORD": "postgres"}, "POSTGRES_PASSWORD"),
        ({"POSTGRES_PASSWORD": "password"}, "POSTGRES_PASSWORD"),
        (
            {"DATABASE_URL": "postgresql://hermes:postgres@db:5432/hermes"},
            "DATABASE_URL",
        ),
        ({"QDRANT_API_KEY": ""}, "QDRANT_API_KEY"),
        ({"QDRANT_API_KEY": "changeme"}, "QDRANT_API_KEY"),
    ],
)
def test_production_rejects_known_defaults(override, fragment):
    env = {**_OK, **override}
    errors = validate_runtime_secrets(env)
    assert errors, env
    assert any(fragment in msg for msg in errors)


def test_enforce_exits_on_unsafe_production(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("POSTGRES_PASSWORD", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/hermes")
    monkeypatch.setenv("QDRANT_API_KEY", "")
    with pytest.raises(SystemExit) as exc:
        enforce_runtime_secrets()
    assert exc.value.code == 1


def test_enforce_noop_outside_production(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    enforce_runtime_secrets()
