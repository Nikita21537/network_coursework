from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from ..protocol.messages import Contact

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AddResult:


    added: bool = False
    updated: bool = False
    moved_lru_to_tail: bool = False
    evicted_dead_lru: bool = False
    rejected_full_alive: bool = False


class KBucket:


    def __init__(
        self,
        capacity: int,
        range_low: int,
        range_high: int,
        index: int = -1,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        if range_low < 0 or range_high < range_low:
            raise ValueError("invalid range")
        self._capacity = capacity
        self._range_low = range_low
        self._range_high = range_high
        self._index = index
        self._contacts: list[Contact] = []


    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def range_low(self) -> int:
        return self._range_low

    @property
    def range_high(self) -> int:
        return self._range_high

    @property
    def index(self) -> int:
        return self._index

    @property
    def contacts(self) -> list[Contact]:

        return list(self._contacts)

    @property
    def size(self) -> int:
        return len(self._contacts)

    def __len__(self) -> int:
        return len(self._contacts)

    def __contains__(self, node_id: bytes) -> bool:
        return any(c.node_id == node_id for c in self._contacts)

    def covers(self, distance: int) -> bool:
        return self._range_low <= distance <= self._range_high


    def get(self, node_id: bytes) -> Contact | None:
        for c in self._contacts:
            if c.node_id == node_id:
                return c
        return None

    def add_or_update(
        self,
        contact: Contact,
        ping_lru: Callable[[Contact], bool],
    ) -> AddResult:


        for i, existing in enumerate(self._contacts):
            if existing.node_id == contact.node_id:

                if existing.identity_public_key != contact.identity_public_key:
                    log.warning(
                        "kbucket[%d]: contact with same node_id but "
                        "different public key; rejecting",
                        self._index,
                    )
                    return AddResult()
                self._contacts.pop(i)
                self._contacts.append(contact)
                return AddResult(updated=True)


        if len(self._contacts) < self._capacity:
            self._contacts.append(contact)
            return AddResult(added=True)


        lru = self._contacts[0]
        alive = ping_lru(lru)

        if alive:

            self._contacts.pop(0)
            self._contacts.append(lru)
            return AddResult(
                rejected_full_alive=True,
                moved_lru_to_tail=True,
            )


        self._contacts.pop(0)
        self._contacts.append(contact)
        return AddResult(added=True, evicted_dead_lru=True)

    def touch(self, node_id: bytes) -> bool:

        for i, existing in enumerate(self._contacts):
            if existing.node_id == node_id:
                self._contacts.pop(i)
                self._contacts.append(existing)
                return True
        return False

    def remove(self, node_id: bytes) -> bool:
        for i, existing in enumerate(self._contacts):
            if existing.node_id == node_id:
                self._contacts.pop(i)
                return True
        return False


    def find_closest(
        self, target_node_id: bytes, limit: int
    ) -> list[Contact]:

        from .contact import xor_distance

        target = int.from_bytes(target_node_id, "big")
        ordered = sorted(
            self._contacts, key=lambda c: xor_distance(c.node_id, target)
        )
        return ordered[:limit]

    def __repr__(self) -> str:
        return (
            f"KBucket(index={self._index}, size={len(self._contacts)}"
            f"/{self._capacity}, range=[{self._range_low}, {self._range_high}])"
        )