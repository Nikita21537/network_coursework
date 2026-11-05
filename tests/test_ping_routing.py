from __future__ import annotations

import socket
import tempfile
import time
import unittest
from pathlib import Path

from p2pnode.config import Config
from p2pnode.node.node import Node, RpcError
from p2pnode.protocol.constants import PROTOCOL_VERSION
from p2pnode.protocol.messages import Contact, Pong


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _make_config(port: int, state_dir: Path) -> Config:
    return Config(
        node_state_dir=state_dir,
        listen_host="127.0.0.1",
        listen_port=port,
        bootstrap_peers=(),
        node_id_bits=256,
        k_bucket_size=3,
        alpha=3,
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


class PingRoutingTests(unittest.TestCase):
    def test_t210_ping_updates_routing_both_sides(self) -> None:
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
                self.assertEqual(len(n1.routing), 0)
                self.assertEqual(len(n2.routing), 0)

                contact2 = _contact_for(n2)
                pong = n1.ping(contact2)
                self.assertIsInstance(pong, Pong)

                # A добавил B в routing (после PONG).
                self.assertIn(n2.identity.node_id, n1.routing)
                # B добавил A в routing (PingHandler до отправки PONG).
                self.assertIn(n1.identity.node_id, n2.routing)
                self.assertEqual(len(n1.routing), 1)
                self.assertEqual(len(n2.routing), 1)
            finally:
                n1.stop()
                n2.stop()

    def test_t210_dead_contact_not_added(self) -> None:

        with tempfile.TemporaryDirectory() as d:
            port = free_port()
            node = Node(_make_config(port, Path(d)))
            node.start()
            try:
                time.sleep(0.2)
                dead = free_port()
                # Контакт с заведомо мёртвым портом; используем реальную
                # идентичность второго (временного) узла, чтобы пройти
                # валидацию Contact.
                with tempfile.TemporaryDirectory() as d2:
                    other = Node(_make_config(free_port(), Path(d2)))
                    # не запускаем
                    dead_contact = Contact(
                        node_id=other.identity.node_id,
                        identity_algorithm=other.identity.algorithm,
                        identity_public_key=other.identity.public_key,
                        host="127.0.0.1",
                        port=dead,
                    )
                with self.assertRaises(RpcError):
                    node.ping(dead_contact)
                self.assertEqual(len(node.routing), 0)
            finally:
                node.stop()

    def test_send_ping_only_returns_false_on_dead(self) -> None:
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            node = Node(_make_config(free_port(), Path(d1)))
            other = Node(_make_config(free_port(), Path(d2)))
            dead = free_port()
            dead_contact = Contact(
                node_id=other.identity.node_id,
                identity_algorithm=other.identity.algorithm,
                identity_public_key=other.identity.public_key,
                host="127.0.0.1",
                port=dead,
            )
            self.assertFalse(node._send_ping_only(dead_contact))

    def test_send_ping_only_returns_true_on_alive(self) -> None:
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
                self.assertTrue(n1._send_ping_only(_contact_for(n2)))
            finally:
                n1.stop()
                n2.stop()


if __name__ == "__main__":
    unittest.main()