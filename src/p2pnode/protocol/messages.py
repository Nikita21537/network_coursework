from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Contact:
    node_id: bytes  # 32 байта
    host: str
    port: int

    def __post_init__(self) -> None:
        if len(self.node_id) != 32:
            raise ValueError("node_id must be 32 bytes")
        if not (0 < self.port < 65536):
            raise ValueError("port out of range")
        if not self.host:
            raise ValueError("host must be non-empty")


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