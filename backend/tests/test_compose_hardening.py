"""Default compose is safe for a self-hosted pilot; docker.sock is opt-in."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_prod_compose_does_not_mount_docker_sock_or_publish_data_stores():
    text = (ROOT / "docker-compose.yml").read_text()
    assert "/var/run/docker.sock" not in text
    assert "postgres:postgres" not in text
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}" in text
    assert "QDRANT_API_KEY: ${QDRANT_API_KEY:?set QDRANT_API_KEY in .env}" in text
    assert "JWT_SECRET: ${JWT_SECRET:?set JWT_SECRET in .env}" in text
    assert "QDRANT__SERVICE__API_KEY" in text
    assert "127.0.0.1:9119:8080" in text
    assert '"8000:8000"' not in text
    assert '"5432:5432"' not in text
    assert '"6333:6333"' not in text
    assert "cap_drop" in text
    assert "no-new-privileges:true" in text
    assert "ENV: production" in text
    assert "ALLOW_LOCAL_AUTH_FALLBACK: ${ALLOW_LOCAL_AUTH_FALLBACK:-0}" in text
    assert "CODE_AGENTS_ENABLED: ${CODE_AGENTS_ENABLED:-false}" in text
    assert "HERMES_REQUIRE_SIGNING: ${HERMES_REQUIRE_SIGNING:-false}" in text


def test_docker_sock_overlay_is_opt_in_with_warning():
    text = (ROOT / "docker-compose.docker-sock.yml").read_text()
    assert "/var/run/docker.sock:/var/run/docker.sock" in text
    assert "profiles:" in text
    assert "docker-sock" in text
    assert "WARNING" in text
    assert "host-root" in text.lower() or "host root" in text.lower()


def test_dev_compose_is_marked_dev_only_and_binds_localhost():
    text = (ROOT / "docker-compose.dev.yml").read_text()
    assert "DEV ONLY" in text
    assert "127.0.0.1:8000:8000" in text
    assert "127.0.0.1:5173:5173" in text
    assert "127.0.0.1:6333:6333" in text
    assert "/var/run/docker.sock" not in text
    assert "ENV: development" in text
    assert 'CODE_AGENTS_ENABLED: "true"' in text
    assert "HERMES_REQUIRE_SIGNING: ${HERMES_REQUIRE_SIGNING:-false}" in text


def test_prod_dockerfiles_define_non_root_user():
    backend = (ROOT / "backend/Dockerfile").read_text()
    frontend = (ROOT / "frontend/Dockerfile").read_text()
    sandbox = (ROOT / "sandbox/Dockerfile").read_text()
    assert "USER hermes" in backend
    assert "useradd --uid 10001" in backend
    assert "pytest" not in backend
    assert "COPY hermes_sdk/" in backend
    assert "USER nginx" in frontend
    assert "EXPOSE 8080" in frontend
    assert "USER sandbox" in sandbox
    assert "useradd --uid 10002" in sandbox


def test_env_example_does_not_ship_default_secrets():
    example = (ROOT / ".env.example").read_text()
    assert "postgres:postgres" not in example
    assert "JWT_SECRET=" in example
    assert "POSTGRES_PASSWORD=" in example
    assert "QDRANT_API_KEY=" in example
    assert "STRIPE_SECRET_KEY=" in example
    assert "your_stripe_secret_key_here" not in example
    assert "CODE_AGENTS_ENABLED=false" in example
    assert "HERMES_REQUIRE_SIGNING=false" in example
