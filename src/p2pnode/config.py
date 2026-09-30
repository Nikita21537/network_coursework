from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(path: str | Path) -> dict[str, str]:
    data: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config file not found: {p}")
    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid config line: {raw_line!r}")
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip()
    return data


@dataclass(frozen=True)
class Config:
    node_state_dir: Path
    listen_host: str
    listen_port: int
    bootstrap_peers: tuple[str, ...]
    node_id_bits: int
    k_bucket_size: int
    alpha: int
    connect_timeout_ms: int
    read_timeout_ms: int
    ping_timeout_ms: int
    max_frame_payload: int
    protocol_version: int
    log_level: str

    @classmethod
    def load(cls, config_file: str | None = None) -> "Config":
        merged: dict[str, str] = {}
        if config_file:
            merged.update(_load_env_file(config_file))
        for key in (
            "NODE_STATE_DIR",
            "LISTEN_HOST",
            "LISTEN_PORT",
            "BOOTSTRAP_PEERS",
            "NODE_ID_BITS",
            "K_BUCKET_SIZE",
            "ALPHA",
            "CONNECT_TIMEOUT_MS",
            "READ_TIMEOUT_MS",
            "PING_TIMEOUT_MS",
            "MAX_FRAME_PAYLOAD",
            "PROTOCOL_VERSION",
            "LOG_LEVEL",
        ):
            if key in os.environ:
                merged[key] = os.environ[key]

        node_state_dir = Path(merged.get("NODE_STATE_DIR", "./state/default"))
        listen_host = merged.get("LISTEN_HOST", "0.0.0.0")
        listen_port = int(merged.get("LISTEN_PORT", "9101"))
        bootstrap_raw = merged.get("BOOTSTRAP_PEERS", "")
        bootstrap = tuple(p.strip() for p in bootstrap_raw.split(",") if p.strip())

        node_id_bits = int(merged.get("NODE_ID_BITS", "256"))
        if node_id_bits != 256:
            raise ValueError("NODE_ID_BITS must be 256 on stages 1-2")

        k_bucket_size = int(merged.get("K_BUCKET_SIZE", "3"))
        if k_bucket_size not in (3, 4):
            raise ValueError("K_BUCKET_SIZE must be 3 (basic) or 4 (advanced)")

        alpha = int(merged.get("ALPHA", "3"))
        if alpha != 3:
            raise ValueError("ALPHA must be 3 on stages 1-2")

        return cls(
            node_state_dir=node_state_dir,
            listen_host=listen_host,
            listen_port=listen_port,
            bootstrap_peers=bootstrap,
            node_id_bits=node_id_bits,
            k_bucket_size=k_bucket_size,
            alpha=alpha,
            connect_timeout_ms=int(merged.get("CONNECT_TIMEOUT_MS", "3000")),
            read_timeout_ms=int(merged.get("READ_TIMEOUT_MS", "5000")),
            ping_timeout_ms=int(merged.get("PING_TIMEOUT_MS", "5000")),
            max_frame_payload=int(merged.get("MAX_FRAME_PAYLOAD", "65536")),
            protocol_version=int(merged.get("PROTOCOL_VERSION", "1")),
            log_level=merged.get("LOG_LEVEL", "INFO").upper(),
        )