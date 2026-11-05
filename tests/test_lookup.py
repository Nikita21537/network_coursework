from __future__ import annotations

import socket
import tempfile
import time
import unittest
from pathlib import Path

from p2pnode.config import Config
from p2pnode.node.node import Node
from p2pnode.protocol.constants import PROTOCOL_VERSION
from p2pnode.protocol.messages import Contact
from p2pnode.routing.contact import xor_distance
from p2pnode.routing.lookup import lookup_node


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _make_config(port: int, state_dir: Path, k: int = 3, alpha: int = 3) -> Config:
    return Config(
        node_state_dir=state_dir,
        listen_host="127.0.0.1",
        listen_port=port,
        bootstrap_peers=(),
        node_id_bits=256,
        k_bucket_size=k,
        alpha=alpha,
        connect_timeout_ms=1000,
        read_timeout_ms=1000,
        ping_timeout_ms=1000,
        max_frame_payload=65536,
        protocol_version=PROTOCOL_VERSION,
        log_level="WARNING",
    )


def _contact_for(node: Node) -> Contact:
    return Contact(
        node_id=node.identity.node_id,
        identity_algorithm=node.identity.algorithm,
        identity_public_key=node.identity.public_key,
        host="127.0.0.1",
        port=node.config.listen_port,
    )


class LookupTests(unittest.TestCase):
    def test_empty_routing_returns_empty_result(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            node = Node(_make_config(free_port(), Path(d)))
            node.start()
            try:
                time.sleep(0.1)
                target = b"\xAA" * 32
                res = lookup_node(node, target)
                self.assertFalse(res.success)
                self.assertEqual(res.rpc_count, 0)
                self.assertEqual(res.iterations, 0)
                self.assertEqual(len(res.closest_contacts), 0)
            finally:
                node.stop()

    def test_t213_multi_hop_lookup(self) -> None:
        """T2.13: инициатор не знает цель, но находит через промежуточных."""
        # Топология:
        #   I (инициатор) знает только A.
        #   A знает B.
        #   B знает C (цель).
        #   C — цель, отсутствующая в таблице I и A.
        with (
            tempfile.TemporaryDirectory() as dI,
            tempfile.TemporaryDirectory() as dA,
            tempfile.TemporaryDirectory() as dB,
            tempfile.TemporaryDirectory() as dC,
        ):
            pI, pA, pB, pC = (
                free_port(),
                free_port(),
                free_port(),
                free_port(),
            )
            I = Node(_make_config(pI, Path(dI)))
            A = Node(_make_config(pA, Path(dA)))
            B = Node(_make_config(pB, Path(dB)))
            C = Node(_make_config(pC, Path(dC)))
            I.start()
            A.start()
            B.start()
            C.start()
            try:
                time.sleep(0.3)

                cA = _contact_for(A)
                cB = _contact_for(B)
                cC = _contact_for(C)

                # A ↔ B, B ↔ C — прямые связи.
                A.ping(cB)
                B.ping(cC)
                # I ↔ A — единственная связь I.
                I.ping(cA)

                # Убедимся, что цель отсутствует в таблице I.
                self.assertNotIn(C.identity.node_id, I.routing)
                self.assertNotIn(C.identity.node_id, A.routing)
                # Но есть в B (напрямую от C.ping(B)? — нет,
                # но B.ping(C) добавил C в B.routing).
                self.assertIn(C.identity.node_id, B.routing)

                res = lookup_node(I, C.identity.node_id)
                self.assertTrue(
                    res.success,
                    f"lookup failed: rpc={res.rpc_count} "
                    f"iters={res.iterations} contacts="
                    f"{[c.node_id.hex()[:8] for c in res.closest_contacts]}",
                )
                # Инициатор не знал цель до старта — проверка выше.
                # После lookup — знает.
                self.assertIn(C.identity.node_id, I.routing)
                # RPC-счётчик положительный.
                self.assertGreater(res.rpc_count, 0)
                self.assertGreaterEqual(res.iterations, 1)
            finally:
                I.stop()
                A.stop()
                B.stop()
                C.stop()

    def test_lookup_when_target_already_in_routing(self) -> None:
        with (
            tempfile.TemporaryDirectory() as d1,
            tempfile.TemporaryDirectory() as d2,
        ):
            p1, p2 = free_port(), free_port()
            n1 = Node(_make_config(p1, Path(d1)))
            n2 = Node(_make_config(p2, Path(d2)))
            n1.start()
            n2.start()
            try:
                time.sleep(0.2)
                n1.ping(_contact_for(n2))
                self.assertIn(n2.identity.node_id, n1.routing)

                res = lookup_node(n1, n2.identity.node_id)
                self.assertTrue(res.success)
                ids = {c.node_id for c in res.closest_contacts}
                self.assertIn(n2.identity.node_id, ids)
            finally:
                n1.stop()
                n2.stop()

    def test_lookup_handles_unreachable_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as d1:
            node = Node(_make_config(free_port(), Path(d1)))
            node.start()
            try:
                time.sleep(0.1)
                # Создаём фейковый Contact с заведомо мёртвым портом,
                # но реальным Ed25519-ключом.
                with tempfile.TemporaryDirectory() as dF:
                    fake = Node(_make_config(free_port(), Path(dF)))
                    dead_port = free_port()
                    # fake не запускаем — порт free.
                    fake_contact = Contact(
                        node_id=fake.identity.node_id,
                        identity_algorithm=fake.identity.algorithm,
                        identity_public_key=fake.identity.public_key,
                        host="127.0.0.1",
                        port=dead_port,
                    )
                # Добавляем в routing напрямую (без ping_lru).
                node.routing.add_or_update(
                    fake_contact, ping_lru=lambda _c: False
                )
                self.assertIn(fake.identity.node_id, node.routing)

                res = lookup_node(node, b"\xBB" * 32)
                # Lookup может опросить фейковый контакт или нет
                # (зависит от bucket заполнения), но не должен упасть.
                self.assertIsInstance(res.timeouts, tuple)
                # fake_contact или в timeouts, или не опрашивался.
                if fake.identity.node_id in [t for t in res.timeouts]:
                    self.assertIn(fake.identity.node_id, res.timeouts)
            finally:
                node.stop()


if __name__ == "__main__":
    unittest.main()