from __future__ import annotations

import socket
import tempfile
import time
import unittest
from pathlib import Path

from p2pnode.config import Config
from p2pnode.node.bootstrap import parse_peer
from p2pnode.node.node import Node
from p2pnode.protocol.constants import PROTOCOL_VERSION


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _make_config(port: int, state_dir: Path, bootstrap=()) -> Config:
    return Config(
        node_state_dir=state_dir,
        listen_host="127.0.0.1",
        listen_port=port,
        bootstrap_peers=tuple(bootstrap),
        node_id_bits=256,
        k_bucket_size=3,
        alpha=3,
        connect_timeout_ms=2000,
        read_timeout_ms=3000,
        ping_timeout_ms=3000,
        max_frame_payload=65536,
        protocol_version=PROTOCOL_VERSION,
        log_level="WARNING",
    )


class BootstrapTests(unittest.TestCase):
    def test_parse_peer_valid(self) -> None:
        self.assertEqual(parse_peer("127.0.0.1:9101"), ("127.0.0.1", 9101))
        self.assertEqual(parse_peer("node:1"), ("node", 1))

    def test_parse_peer_invalid(self) -> None:
        for bad in ("", "noport", "host:", ":9101", "host:notint", "host:0", "host:99999"):
            with self.assertRaises(ValueError):
                parse_peer(bad)

    def test_t212_new_node_has_contact_after_join(self) -> None:

        with (
            tempfile.TemporaryDirectory() as d1,
            tempfile.TemporaryDirectory() as d2,
        ):
            p1, p2 = free_port(), free_port()
            seed = Node(_make_config(p1, Path(d1)))
            seed.start()
            try:
                time.sleep(0.2)
                joiner = Node(
                    _make_config(
                        p2, Path(d2), bootstrap=[f"127.0.0.1:{p1}"]
                    )
                )
                joiner.start()
                try:
                    time.sleep(0.2)
                    self.assertEqual(len(joiner.routing), 0)

                    result = joiner.join([f"127.0.0.1:{p1}"])
                    self.assertTrue(result.success)
                    self.assertIsNotNone(result.bootstrap_contact)
                    self.assertEqual(
                        result.bootstrap_contact.node_id,
                        seed.identity.node_id,
                    )
                    self.assertGreaterEqual(len(joiner.routing), 1)
                    self.assertIn(seed.identity.node_id, joiner.routing)
                    # Self-lookup выполнен.
                    self.assertIsNotNone(result.self_lookup_result)
                finally:
                    joiner.stop()
            finally:
                seed.stop()

    def test_t214_lookup_works_without_bootstrap(self) -> None:

        from p2pnode.routing.lookup import lookup_node

        with (
            tempfile.TemporaryDirectory() as d1,
            tempfile.TemporaryDirectory() as d2,
            tempfile.TemporaryDirectory() as d3,
        ):
            p1, p2, p3 = free_port(), free_port(), free_port()
            n1 = Node(_make_config(p1, Path(d1)))
            n1.start()
            try:
                time.sleep(0.2)
                n2 = Node(
                    _make_config(
                        p2, Path(d2), bootstrap=[f"127.0.0.1:{p1}"]
                    )
                )
                n2.start()
                try:
                    time.sleep(0.2)
                    r2 = n2.join([f"127.0.0.1:{p1}"])
                    self.assertTrue(r2.success)

                    n3 = Node(
                        _make_config(
                            p3, Path(d3), bootstrap=[f"127.0.0.1:{p2}"]
                        )
                    )
                    n3.start()
                    try:
                        time.sleep(0.2)
                        r3 = n3.join([f"127.0.0.1:{p2}"])
                        self.assertTrue(r3.success)


                        n1.stop()
                        time.sleep(0.2)


                        res = lookup_node(n3, n2.identity.node_id)
                        self.assertTrue(
                            res.success,
                            f"n3 → n2 lookup failed after bootstrap "
                            f"shutdown: rpc={res.rpc_count}",
                        )
                    finally:
                        n3.stop()
                finally:
                    n2.stop()
            finally:
                n1.stop()


if __name__ == "__main__":
    unittest.main()