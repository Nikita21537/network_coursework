from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)



_PRIVATE_KEY_FILE = "identity.priv"
_PUBLIC_KEY_FILE = "identity.pub"


_CANONICAL_PREFIX = b"ed25519:"


IDENTITY_ALGORITHM = "ed25519"


_RAW_PUBLIC_KEY_BYTES = 32


def canonical_encode_public_key(public_key: bytes) -> bytes:

    if len(public_key) != _RAW_PUBLIC_KEY_BYTES:
        raise ValueError(
            f"Ed25519 public key must be 32 raw bytes, got {len(public_key)}"
        )
    return _CANONICAL_PREFIX + public_key


def compute_node_id(public_key: bytes) -> bytes:
    return hashlib.sha256(canonical_encode_public_key(public_key)).digest()


@dataclass(frozen=True)
class Identity:


    node_id: bytes
    public_key: bytes
    _private_key: Ed25519PrivateKey

    @property
    def node_id_hex(self) -> str:
        return self.node_id.hex()

    @property
    def public_key_hex(self) -> str:
        return self.public_key.hex()

    @property
    def short_id(self) -> str:
        return self.node_id_hex[:8]

    @property
    def algorithm(self) -> str:
        return IDENTITY_ALGORITHM

    def sign(self, data: bytes) -> bytes:
        return self._private_key.sign(data)

    def verify(self, signature: bytes, data: bytes) -> bool:
        try:
            self._public_key_obj().verify(signature, data)
            return True
        except Exception:
            return False

    def _public_key_obj(self) -> Ed25519PublicKey:
        return Ed25519PublicKey.from_public_bytes(self.public_key)

    @staticmethod
    def load_or_create(state_dir: Path) -> "Identity":
        state_dir.mkdir(parents=True, exist_ok=True)
        priv_path = state_dir / _PRIVATE_KEY_FILE
        pub_path = state_dir / _PUBLIC_KEY_FILE

        if priv_path.exists():
            if not pub_path.exists():
                raise RuntimeError(
                    f"identity.priv exists but identity.pub is missing in {state_dir}; "
                    "remove identity.priv to regenerate a new identity"
                )
            return Identity._load(priv_path, pub_path)
        else:
            if pub_path.exists():
                raise RuntimeError(
                    f"identity.pub exists but identity.priv is missing in {state_dir}; "
                    "remove identity.pub to regenerate a new identity"
                )
            return Identity._create(priv_path, pub_path)

    @staticmethod
    def _load(priv_path: Path, pub_path: Path) -> "Identity":

        priv_data = priv_path.read_bytes()
        try:
            private_key = serialization.load_pem_private_key(
                priv_data, password=None
            )
        except ValueError as exc:
            raise ValueError(
                f"invalid identity.priv at {priv_path}: {exc}"
            ) from exc
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError(
                f"identity.priv at {priv_path} is not an Ed25519 key"
            )

        pub_data = pub_path.read_bytes()
        if len(pub_data) != _RAW_PUBLIC_KEY_BYTES:
            raise ValueError(
                f"identity.pub at {pub_path} must be 32 raw bytes, "
                f"got {len(pub_data)}"
            )


        derived = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        )
        if derived != pub_data:
            raise ValueError(
                f"identity.pub at {pub_path} does not match identity.priv"
            )

        node_id = compute_node_id(pub_data)
        return Identity(
            node_id=node_id,
            public_key=pub_data,
            _private_key=private_key,
        )

    @staticmethod
    def _create(priv_path: Path, pub_path: Path) -> "Identity":
        private_key = Ed25519PrivateKey.generate()
        pub_bytes = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        )
        priv_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )


        tmp_priv = priv_path.with_suffix(".tmp")
        tmp_priv.write_bytes(priv_pem)
        try:
            os.chmod(tmp_priv, 0o600)
        except OSError:
            pass  # Windows — best-effort
        os.replace(tmp_priv, priv_path)


        tmp_pub = pub_path.with_suffix(".tmp")
        tmp_pub.write_bytes(pub_bytes)
        os.replace(tmp_pub, pub_path)

        node_id = compute_node_id(pub_bytes)
        return Identity(
            node_id=node_id,
            public_key=pub_bytes,
            _private_key=private_key,
        )