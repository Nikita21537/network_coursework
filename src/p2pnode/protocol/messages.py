from __future__ import annotations

from dataclasses import dataclass, field

from ..identity.node_id import compute_node_id


@dataclass(frozen=True)
class Contact:
    node_id: bytes               # 32 байта
    identity_algorithm: str      # "ed25519" на этапах 2+
    identity_public_key: bytes   # 32 сырых байта Ed25519
    host: str
    port: int

    def __post_init__(self) -> None:
        if len(self.node_id) != 32:
            raise ValueError("node_id must be 32 bytes")
        if self.identity_algorithm != "ed25519":
            raise ValueError(
                f"unsupported identity_algorithm: {self.identity_algorithm!r}"
            )
        if len(self.identity_public_key) != 32:
            raise ValueError("identity_public_key must be 32 raw bytes")
        if not (0 < self.port < 65536):
            raise ValueError("port out of range")
        if not self.host:
            raise ValueError("host must be non-empty")


        derived = compute_node_id(self.identity_public_key)
        if derived != self.node_id:
            raise ValueError(
                "node_id does not match SHA-256(canonical_encode(identity_public_key))"
            )


@dataclass(frozen=True)
class Ping:
    sender: Contact
    timestamp_ms: int


@dataclass(frozen=True)
class Pong:
    responder: Contact
    ping_timestamp_ms: int
    responder_timestamp_ms: int


@dataclass(frozen=True)
class FindNodeRequest:
    sender: Contact
    target_node_id: bytes

    def __post_init__(self) -> None:
        if len(self.target_node_id) != 32:
            raise ValueError("target_node_id must be 32 bytes")


@dataclass(frozen=True)
class FindNodeResponse:
    responder: Contact
    target_node_id: bytes
    contacts: tuple[Contact, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if len(self.target_node_id) != 32:
            raise ValueError("target_node_id must be 32 bytes")


@dataclass(frozen=True)
class ErrorMessage:
    code: str
    message: str