from __future__ import annotations

from typing import Iterable, Union

from ..protocol.messages import Contact

DistanceInput = Union[bytes, int]


def xor_distance(a: bytes, b: DistanceInput) -> int:

    if len(a) != 32:
        raise ValueError("a must be 32 bytes")
    ai = int.from_bytes(a, "big")
    bi = b if isinstance(b, int) else int.from_bytes(b, "big")
    return ai ^ bi


def sort_by_distance(
    contacts: Iterable[Contact], target: bytes, limit: int
) -> list[Contact]:

    if len(target) != 32:
        raise ValueError("target must be 32 bytes")
    target_int = int.from_bytes(target, "big")
    ordered = sorted(contacts, key=lambda c: xor_distance(c.node_id, target_int))
    return ordered[:limit]