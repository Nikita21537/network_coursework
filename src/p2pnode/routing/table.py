from __future__ import annotations

import logging
from dataclasses import dataclass

from ..protocol.messages import Contact
from .contact import xor_distance
from .kbucket import AddResult, KBucket

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutingAddResult:


    added: bool = False
    updated: bool = False
    moved_lru_to_tail: bool = False
    evicted_dead_lru: bool = False
    rejected_full_alive: bool = False
    rejected_self: bool = False
    bucket_index: int = -1


class RoutingTable:


    NUM_BUCKETS = 256

    def __init__(self, local_node_id: bytes, k_bucket_size: int) -> None:
        if len(local_node_id) != 32:
            raise ValueError("local_node_id must be 32 bytes")
        if k_bucket_size <= 0:
            raise ValueError("k_bucket_size must be > 0")
        self._local_node_id = local_node_id
        self._k = k_bucket_size
        self._buckets: list[KBucket] = []
        for i in range(self.NUM_BUCKETS):
            if i < 255:
                low = 1 << i
                high = (1 << (i + 1)) - 1
            else:
                low = 1 << 255
                high = (1 << 256) - 1
            self._buckets.append(
                KBucket(
                    capacity=k_bucket_size,
                    range_low=low,
                    range_high=high,
                    index=i,
                )
            )


    @property
    def local_node_id(self) -> bytes:
        return self._local_node_id

    @property
    def k_bucket_size(self) -> int:
        return self._k

    @property
    def buckets(self) -> list[KBucket]:
        return list(self._buckets)

    def __len__(self) -> int:
        return sum(len(b) for b in self._buckets)

    def __contains__(self, node_id: bytes) -> bool:
        return any(node_id in b for b in self._buckets)


    def bucket_index_for(self, node_id: bytes) -> int:

        if len(node_id) != 32:
            raise ValueError("node_id must be 32 bytes")
        distance = xor_distance(node_id, self._local_node_id)
        if distance == 0:
            return -1
        return distance.bit_length() - 1  # 0..255


    def add_or_update(
        self,
        contact: Contact,
        ping_lru,
    ) -> RoutingAddResult:

        idx = self.bucket_index_for(contact.node_id)
        if idx < 0:
            log.info(
                "routing: rejecting self contact (node_id matches local)"
            )
            return RoutingAddResult(rejected_self=True, bucket_index=-1)

        bucket = self._buckets[idx]
        result: AddResult = bucket.add_or_update(contact, ping_lru)
        return RoutingAddResult(
            added=result.added,
            updated=result.updated,
            moved_lru_to_tail=result.moved_lru_to_tail,
            evicted_dead_lru=result.evicted_dead_lru,
            rejected_full_alive=result.rejected_full_alive,
            bucket_index=idx,
        )

    def remove(self, node_id: bytes) -> bool:
        idx = self.bucket_index_for(node_id)
        if idx < 0:
            return False
        return self._buckets[idx].remove(node_id)


    def get(self, node_id: bytes) -> Contact | None:
        idx = self.bucket_index_for(node_id)
        if idx < 0:
            return None
        return self._buckets[idx].get(node_id)

    def all_contacts(self) -> list[Contact]:
        out: list[Contact] = []
        for b in self._buckets:
            out.extend(b.contacts)
        return out

    def find_closest(
        self, target_node_id: bytes, limit: int
    ) -> list[Contact]:

        if limit <= 0:
            return []
        candidates = self.all_contacts()
        if not candidates:
            return []
        target_int = int.from_bytes(target_node_id, "big")
        ordered = sorted(
            candidates, key=lambda c: xor_distance(c.node_id, target_int)
        )
        return ordered[:limit]


    def snapshot(self) -> list[dict]:

        out: list[dict] = []
        for b in self._buckets:
            if len(b) == 0:
                continue
            out.append(
                {
                    "index": b.index,
                    "capacity": b.capacity,
                    "range_low": b.range_low,
                    "range_high": b.range_high,
                    "size": len(b),
                    "contacts": [
                        {
                            "node_id": c.node_id.hex(),
                            "host": c.host,
                            "port": c.port,
                        }
                        for c in b.contacts
                    ],
                }
            )
        return out

    def __repr__(self) -> str:
        n = sum(1 for b in self._buckets if len(b) > 0)
        return (
            f"RoutingTable(local={self._local_node_id.hex()[:8]}, "
            f"k={self._k}, contacts={len(self)}, buckets_used={n})"
        )