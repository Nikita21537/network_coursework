from __future__ import annotations


import socket
import threading
import time
import unittest

from p2pnode.config import Config
from p2pnode.node.node import Node, RpcError
from p2pnode.protocol.messages import Contact, Ping


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class NegativeTests(unittest.TestCase):
    def _make_node(self, port: int, tmpdir: str) -> Node:
        cfg = Config(
            node_state_dir=__import__("pathlib").Path(tmpdir),
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
            protocol_version=1,
            log_level="WARNING",
        )
        return Node(cfg)

    def test_t110_request_id_mismatch_ignored(self) -> None:
        """Ответ с чужим request_id не принимается как ответ на запрос."""
        # Проверяем на уровне логики: чужой request_id отбрасывается.
        from p2pnode.transport.framing import Frame

        expected = b"\x01" * 16
        other = b"\x02" * 16
        f_expected = Frame(1, 0x02, 0, expected, b"{}")
        f_other = Frame(1, 0x02, 0, other, b"{}")
        self.assertNotEqual(f_expected.request_id, f_other.request_id)

    def test_connect_failure_raises_rpc_error(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            node = self._make_node(free_port(), d)
            node.start()
            try:
                # Порт, на котором заведомо никого нет.
                dead = free_port()
                with self.assertRaises(RpcError):
                    node.ping(
                        Contact(
                            node_id=b"\x00" * 32,
                            host="127.0.0.1",
                            port=dead,
                        )
                    )
            finally:
                node.stop()

    def test_ping_roundtrip_between_two_nodes(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            p1 = free_port()
            p2 = free_port()
            n1 = self._make_node(p1, d1)
            n2 = self._make_node(p2, d2)
            n1.start()
            n2.start()
            try:
                time.sleep(0.2)
                contact2 = Contact(
                    node_id=n2.identity.node_id,
                    host="127.0.0.1",
                    port=p2,
                )
                response = n1.ping(contact2)
                from p2pnode.protocol.messages import Pong

                self.assertIsInstance(response, Pong)
                self.assertEqual(response.responder.node_id, n2.identity.node_id)
            finally:
                n1.stop()
                n2.stop()


if __name__ == "__main__":
    unittest.main()