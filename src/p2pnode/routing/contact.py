from __future__ import annotations

from typing import Iterable

from ..protocol.messages import Contact


def xor_distance(a: bytes, b: bytes) -> int:
    if len(a) != len(b):
        raise ValueError("operands must have equal length")
    return int.from_bytes(a, "big") ^ int.from_bytes(b, "big")


def sort_by_distance(
    contacts: Iterable[Contact], target: bytes, limit: int
) -> list[Contact]:
    ordered = sorted(contacts, key=lambda c: xor_distance(c.node_id, target))
    return ordered[:limit]