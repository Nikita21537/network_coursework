from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

_IDENTITY_FILE = "identity.key"


@dataclass(frozen=True)
class Identity:
    node_id: bytes  # 32 байта
    public_key: bytes

    @staticmethod
    def load_or_create(state_dir: Path) -> "Identity":
        state_dir.mkdir(parents=True, exist_ok=True)
        key_path = state_dir / _IDENTITY_FILE
        if key_path.exists():
            public_key = key_path.read_bytes()
            if len(public_key) != 32:
                raise ValueError("identity.key must be 32 bytes")
        else:
            public_key = secrets.token_bytes(32)
            # Атомарная запись.
            tmp = key_path.with_suffix(".tmp")
            tmp.write_bytes(public_key)
            os.replace(tmp, key_path)
        node_id = hashlib.sha256(public_key).digest()
        return Identity(node_id=node_id, public_key=public_key)

    @property
    def node_id_hex(self) -> str:
        return self.node_id.hex()

    @property
    def short_id(self) -> str:
        return self.node_id_hex[:8]