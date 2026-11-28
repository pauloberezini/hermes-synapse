"""Installation Ed25519 key for signed decision-log checkpoints.

Generated on first use if absent. Private key lives on the data volume at mode
0600. There is no KMS and no remote wrapping: pin the fingerprint at install.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from hermes_audit_verify import (
    checkpoint_payload,
    fingerprint_hex,
    public_key_b64,
)

logger = logging.getLogger("hermes.audit_signing")

DEFAULT_KEY_NAME = "audit_ed25519.key"
_REQUIRE_TRUE = {"1", "true", "yes"}


class SigningUnavailable(Exception):
    """No usable installation key. Message must not include key material."""

_cached: InstallKey | None = None
_logged_fingerprint = False


@dataclass(frozen=True)
class InstallKey:
    """In-memory view of the installation signing key. Private key is not printed."""

    installation_id: str
    raw_public: bytes
    fingerprint: str
    public_key: str
    _private: Ed25519PrivateKey

    def sign(self, data: bytes) -> bytes:
        return self._private.sign(data)

    def public_info(self) -> dict[str, str]:
        return {
            "installation_id": self.installation_id,
            "public_key": self.public_key,
            "pubkey_fingerprint": self.fingerprint,
        }


def key_path() -> Path:
    """Private-key path. ``HERMES_AUDIT_KEY_PATH`` overrides the data-volume default."""
    override = os.environ.get("HERMES_AUDIT_KEY_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / DEFAULT_KEY_NAME


def require_signing() -> bool:
    """True only for an explicit opt-in. Unset and unrecognised values stay off."""
    return os.environ.get("HERMES_REQUIRE_SIGNING", "").strip().lower() in _REQUIRE_TRUE


def reset_for_tests() -> None:
    """Drop the process cache so tests can point at a fresh key file."""
    global _cached, _logged_fingerprint
    _cached = None
    _logged_fingerprint = False


def enforce_install_key() -> None:
    """Startup hook. Fail closed with SystemExit when signing is required."""
    try:
        ensure_install_key()
    except SigningUnavailable as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:
        if require_signing():
            print("FATAL: audit signing key init failed.", file=sys.stderr)
            raise SystemExit(1) from None
        logger.warning("audit signing key init failed: %s", exc)


def ensure_install_key() -> InstallKey:
    """Load or create the installation key. Logs fingerprint once per process.

    When ``HERMES_REQUIRE_SIGNING`` is on, never create a key: missing, unreadable,
    wrong type, or mode other than ``0600`` raises ``SigningUnavailable``.
    """
    global _cached, _logged_fingerprint
    if require_signing():
        key = _load_required()
        _cached = key
        _log_fingerprint_once(key)
        return key
    if _cached is not None:
        return _cached
    path = key_path()
    if path.exists():
        key = _load(path)
    else:
        key = _create(path)
    _cached = key
    _log_fingerprint_once(key)
    return key


def _log_fingerprint_once(key: InstallKey) -> None:
    global _logged_fingerprint
    if _logged_fingerprint:
        return
    logger.info(
        "audit signing key fingerprint=%s installation_id=%s",
        key.fingerprint,
        key.installation_id,
    )
    _logged_fingerprint = True


def _load_required() -> InstallKey:
    """Load an existing key. Never create. Never log key material."""
    path = key_path()
    if not path.is_file():
        raise SigningUnavailable(
            "audit signing key missing. Provide a valid Ed25519 key or set HERMES_REQUIRE_SIGNING=false."
        )
    try:
        mode = path.stat().st_mode & 0o777
        if mode != 0o600:
            raise SigningUnavailable("audit signing key must be mode 0600.")
        return _load(path, fix_mode=False)
    except SigningUnavailable:
        raise
    except Exception:
        logger.warning("audit signing key load failed")
        raise SigningUnavailable("audit signing key unreadable or invalid.") from None


def sign_checkpoint(seq: int, head_hash: str, timestamp: str | None = None) -> dict[str, str | int]:
    """Sign one chain head. Returns the checkpoint record stored in the bundle."""
    from datetime import UTC, datetime

    key = ensure_install_key()
    signed_at = timestamp or datetime.now(UTC).isoformat()
    payload = checkpoint_payload(int(seq), head_hash, signed_at, key.installation_id)
    signature = key.sign(payload)
    import base64

    return {
        "seq": int(seq),
        "head_hash": head_hash,
        "timestamp": signed_at,
        "installation_id": key.installation_id,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def _id_path(path: Path) -> Path:
    return Path(str(path) + ".id")


def _create(path: Path) -> InstallKey:
    path.parent.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    _write_private(path, pem)
    installation_id = str(uuid.uuid4())
    _id_path(path).write_text(installation_id + "\n", encoding="utf-8")
    return _from_private(private, installation_id)


def _load(path: Path, *, fix_mode: bool = True) -> InstallKey:
    pem = path.read_bytes()
    if (path.stat().st_mode & 0o777) != 0o600:
        if not fix_mode:
            raise SigningUnavailable("audit signing key must be mode 0600.")
        os.chmod(path, 0o600)
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    loaded = load_pem_private_key(pem, password=None)
    if not isinstance(loaded, Ed25519PrivateKey):
        raise ValueError(f"audit key at {path} is not Ed25519")
    id_file = _id_path(path)
    if id_file.exists():
        installation_id = id_file.read_text(encoding="utf-8").strip()
    else:
        installation_id = str(uuid.uuid4())
        id_file.write_text(installation_id + "\n", encoding="utf-8")
    if not installation_id:
        raise ValueError(f"empty installation id at {id_file}")
    return _from_private(loaded, installation_id)


def _from_private(private: Ed25519PrivateKey, installation_id: str) -> InstallKey:
    raw_public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return InstallKey(
        installation_id=installation_id,
        raw_public=raw_public,
        fingerprint=fingerprint_hex(raw_public),
        public_key=public_key_b64(raw_public),
        _private=private,
    )


def _write_private(path: Path, pem: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(tmp, flags, 0o600)
    try:
        os.write(fd, pem)
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def main() -> int:
    """Print the public key material. ``python -m backend.audit_signing``."""
    import json

    info = ensure_install_key().public_info()
    print(json.dumps(info, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
