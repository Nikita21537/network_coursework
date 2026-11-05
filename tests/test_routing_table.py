from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from p2pnode.identity import Identity
from p2pnode.protocol.messages import Contact
from p2pnode.routing.contact import xor_distance
from p2pnode.routing.table import RoutingTable

VECTORS_PATH = Path(__file__).parent / "vectors" / "xor_vectors.json"


def make_identity() -> Identity:
    with tempfile.TemporaryDirectory() as d:
        ident = Identity.load_or_create(Path(d))
        return Identity(
            node_id=ident.node_id,
            public_key=ident.public_key,
            _private_key=ident._private_key,
        )


def make_contact(
    host: str = "127.0.0.1", port: int = 9101
) -> Contact:
    ident = make_identity()
    return Contact(
        node_id=ident.node_id,
        identity_algorithm=ident.algorithm,
        identity_public_key=ident.public_key,
        host=host,
        port=port,
    )


def always_alive(_c: Contact) -> bool:
    return True


def always_dead(_c: Contact) -> bool:
    return False


class XorMetricTests(unittest.TestCase):

    def test_t25_xor_vectors(self) -> None:
        self.assertTrue(
            VECTORS_PATH.exists(),
            f"vectors file missing: {VECTORS_PATH}",
        )
        data = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertIn("vectors", data)
        self.assertGreaterEqual(len(data["vectors"]), 5)

        for i, v in enumerate(data["vectors"]):
            with self.subTest(vector=i):
                a = bytes.fromhex(v["a_hex"])
                b = bytes.fromhex(v["b_hex"])
                expected = int.from_bytes(
                    bytes.fromhex(v["distance_hex"]), "big"
                )
                self.assertEqual(len(a), 32)
                self.assertEqual(len(b), 32)
                self.assertEqual(xor_distance(a, b), expected)
                # Симметричность
                self.assertEqual(xor_distance(b, a), expected)


class RoutingTableTests(unittest.TestCase):
    def _local_id(self) -> bytes:
        return make_identity().node_id

    def test_bucket_index_for_self_returns_minus_one(self) -> None:
        local = self._local_id()
        t = RoutingTable(local_node_id=local, k_bucket_size=3)
        self.assertEqual(t.bucket_index_for(local), -1)

    def test_bucket_index_for_known_distances(self) -> None:
        # local = 0x000...000
        local = b"\x00" * 32
        t = RoutingTable(local_node_id=local, k_bucket_size=3)
        # node = 1 → расстояние 1 → индекс 0
        self.assertEqual(t.bucket_index_for(b"\x00" * 31 + b"\x01"), 0)
        # node = 2 → расстояние 2 → индекс 1
        self.assertEqual(t.bucket_index_for(b"\x00" * 31 + b"\x02"), 1)
        # node = 3 → расстояние 3 → индекс 1
        self.assertEqual(t.bucket_index_for(b"\x00" * 31 + b"\x03"), 1)
        # node = 4 → расстояние 4 → индекс 2
        self.assertEqual(t.bucket_index_for(b"\x00" * 31 + b"\x04"), 2)
        # node = 2^255 → индекс 255
        b = bytearray(32)
        b[0] = 0x80
        self.assertEqual(t.bucket_index_for(bytes(b)), 255)

    def test_add_self_rejected(self) -> None:
        ident = make_identity()
        t = RoutingTable(local_node_id=ident.node_id, k_bucket_size=3)
        contact = Contact(
            node_id=ident.node_id,
            identity_algorithm=ident.algorithm,
            identity_public_key=ident.public_key,
            host="127.0.0.1",
            port=9101,
        )
        r = t.add_or_update(contact, always_alive)
        self.assertTrue(r.rejected_self)
        self.assertEqual(r.bucket_index, -1)
        self.assertEqual(len(t), 0)

    def test_add_goes_to_correct_bucket(self) -> None:
        local = b"\x00" * 32
        t = RoutingTable(local_node_id=local, k_bucket_size=3)
        c = make_contact()
        r = t.add_or_update(c, always_alive)
        self.assertTrue(r.added)
        expected_idx = xor_distance(c.node_id, local).bit_length() - 1
        self.assertEqual(r.bucket_index, expected_idx)
        self.assertEqual(len(t), 1)
        self.assertIn(c.node_id, t)

    def test_find_closest_sorts_by_xor(self) -> None:
        local = b"\x00" * 32
        t = RoutingTable(local_node_id=local, k_bucket_size=4)
        # Делаем 5 контактов и проверяем, что find_closest возвращает
        # ближайшие и отсортированные.
        contacts = [make_contact() for _ in range(5)]
        for c in contacts:
            t.add_or_update(c, always_alive)
        target = b"\xff" * 32
        ordered = t.find_closest(target, limit=3)
        self.assertEqual(len(ordered), 3)
        target_int = int.from_bytes(target, "big")
        distances = [xor_distance(c.node_id, target_int) for c in ordered]
        self.assertEqual(distances, sorted(distances))

    def test_find_closest_empty_table(self) -> None:
        t = RoutingTable(local_node_id=b"\x00" * 32, k_bucket_size=3)
        self.assertEqual(t.find_closest(b"\xff" * 32, limit=5), [])

    def test_snapshot_format(self) -> None:
        local = b"\x00" * 32
        t = RoutingTable(local_node_id=local, k_bucket_size=3)
        c = make_contact()
        t.add_or_update(c, always_alive)
        snap = t.snapshot()
        self.assertEqual(len(snap), 1)
        entry = snap[0]
        self.assertIn("index", entry)
        self.assertIn("size", entry)
        self.assertEqual(entry["size"], 1)
        self.assertEqual(entry["contacts"][0]["node_id"], c.node_id.hex())


if __name__ == "__main__":
    unittest.main()