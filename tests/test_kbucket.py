from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from p2pnode.identity import Identity
from p2pnode.protocol.messages import Contact
from p2pnode.routing.kbucket import KBucket


def make_contact(
    host: str = "127.0.0.1", port: int = 9101
) -> Contact:
    with tempfile.TemporaryDirectory() as d:
        ident = Identity.load_or_create(Path(d))
        return Contact(
            node_id=ident.node_id,
            identity_algorithm=ident.algorithm,
            identity_public_key=ident.public_key,
            host=host,
            port=port,
        )


def always_alive(_contact: Contact) -> bool:
    return True


def always_dead(_contact: Contact) -> bool:
    return False


class KBucketTests(unittest.TestCase):
    def _bucket(self, capacity: int = 3) -> KBucket:
        return KBucket(capacity=capacity, range_low=1, range_high=2**256 - 1)

    def test_capacity_not_exceeded(self) -> None:
        b = self._bucket(capacity=2)
        c1, c2, c3 = make_contact(), make_contact(), make_contact()
        b.add_or_update(c1, always_alive)
        b.add_or_update(c2, always_alive)
        r = b.add_or_update(c3, always_alive)
        self.assertFalse(r.added)
        self.assertTrue(r.rejected_full_alive)
        self.assertEqual(len(b), 2)

    def test_duplicate_node_id_not_added_twice(self) -> None:
        b = self._bucket(capacity=3)
        c = make_contact()
        r1 = b.add_or_update(c, always_alive)
        r2 = b.add_or_update(c, always_alive)
        self.assertTrue(r1.added)
        self.assertTrue(r2.updated)
        self.assertEqual(len(b), 1)

    def test_t26_insert_into_nonfull_bucket(self) -> None:
        b = self._bucket(capacity=3)
        c1, c2 = make_contact(), make_contact()
        r1 = b.add_or_update(c1, always_alive)
        r2 = b.add_or_update(c2, always_alive)
        self.assertTrue(r1.added)
        self.assertTrue(r2.added)
        self.assertEqual(
            [c.node_id for c in b.contacts],
            [c1.node_id, c2.node_id],
        )

    def test_t27_repeated_observation_moves_to_end(self) -> None:
        b = self._bucket(capacity=3)
        c1, c2, c3 = make_contact(), make_contact(), make_contact()
        b.add_or_update(c1, always_alive)
        b.add_or_update(c2, always_alive)
        b.add_or_update(c3, always_alive)
        r = b.add_or_update(c1, always_alive)
        self.assertTrue(r.updated)
        self.assertEqual(
            [c.node_id for c in b.contacts],
            [c2.node_id, c3.node_id, c1.node_id],
        )

    def test_t28_full_bucket_live_lru_kept(self) -> None:
        b = self._bucket(capacity=3)
        c1, c2, c3 = make_contact(), make_contact(), make_contact()
        b.add_or_update(c1, always_alive)
        b.add_or_update(c2, always_alive)
        b.add_or_update(c3, always_alive)
        new_c = make_contact()

        pings: list[bytes] = []

        def ping_lru(contact: Contact) -> bool:
            pings.append(contact.node_id)
            return True

        r = b.add_or_update(new_c, ping_lru)
        self.assertTrue(r.rejected_full_alive)
        self.assertTrue(r.moved_lru_to_tail)
        self.assertFalse(r.added)
        self.assertEqual(pings, [c1.node_id])
        self.assertEqual(len(b), 3)
        self.assertEqual(
            [c.node_id for c in b.contacts],
            [c2.node_id, c3.node_id, c1.node_id],
        )
        self.assertNotIn(new_c.node_id, b)

    def test_t29_full_bucket_dead_lru_evicted(self) -> None:
        b = self._bucket(capacity=3)
        c1, c2, c3 = make_contact(), make_contact(), make_contact()
        b.add_or_update(c1, always_alive)
        b.add_or_update(c2, always_alive)
        b.add_or_update(c3, always_alive)
        new_c = make_contact()

        pings: list[bytes] = []

        def ping_lru(contact: Contact) -> bool:
            pings.append(contact.node_id)
            return False

        r = b.add_or_update(new_c, ping_lru)
        self.assertTrue(r.added)
        self.assertTrue(r.evicted_dead_lru)
        self.assertEqual(pings, [c1.node_id])
        self.assertEqual(len(b), 3)
        self.assertEqual(
            [c.node_id for c in b.contacts],
            [c2.node_id, c3.node_id, new_c.node_id],
        )
        self.assertNotIn(c1.node_id, b)

    def test_update_address_of_existing_contact(self) -> None:
        b = self._bucket(capacity=3)
        c1 = make_contact(host="127.0.0.1", port=9101)
        c2 = make_contact()
        b.add_or_update(c1, always_alive)
        b.add_or_update(c2, always_alive)
        c1_new = Contact(
            node_id=c1.node_id,
            identity_algorithm=c1.identity_algorithm,
            identity_public_key=c1.identity_public_key,
            host="192.168.1.1",
            port=9200,
        )
        r = b.add_or_update(c1_new, always_alive)
        self.assertTrue(r.updated)
        self.assertEqual(b.contacts[-1].host, "192.168.1.1")
        self.assertEqual(b.contacts[-1].port, 9200)

    def test_conflicting_public_key_rejected(self) -> None:
        b = self._bucket(capacity=3)
        c1 = make_contact()
        b.add_or_update(c1, always_alive)
        c2 = make_contact()
        r = b.add_or_update(c2, always_alive)
        self.assertTrue(r.added or r.rejected_full_alive)


if __name__ == "__main__":
    unittest.main()