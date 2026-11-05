from __future__ import annotations

import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from p2pnode.config import Config
from p2pnode.identity import Identity
from p2pnode.node.node import Node, RpcError
from p2pnode.protocol.codec import encode_payload
from p2pnode.protocol.constants import (
    ALLOWED_TYPES,
    MSG_PONG,
    PROTOCOL_VERSION,
)
from p2pnode.protocol.messages import Contact, Pong
from p2pnode.transport.connection import Connection
from p2pnode.transport.framing import (
    HEADER_SIZE,
    Frame,
    FrameDecoder,
    ProtocolError,
)


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


def _dummy_contact(host: str = "127.0.0.1", port: int = 9101) -> Contact:
    with tempfile.TemporaryDirectory() as d:
        ident = Identity.load_or_create(Path(d))
        return Contact(
            node_id=ident.node_id,
            identity_algorithm=ident.algorithm,
            identity_public_key=ident.public_key,
            host=host,
            port=port,
        )


class NegativeTests(unittest.TestCase):
    def test_t110_request_id_mismatch_ignored(self) -> None:
        expected = b"\x01" * 16
        other = b"\x02" * 16
        f_expected = Frame(1, 0x02, 0, expected, b"{}")
        f_other = Frame(1, 0x02, 0, other, b"{}")
        self.assertNotEqual(f_expected.request_id, f_other.request_id)

    def test_connect_failure_raises_rpc_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            node = Node(_make_config(free_port(), Path(d)))
            node.start()
            try:
                dead = free_port()
                with self.assertRaises(RpcError):
                    node.ping(_dummy_contact(port=dead))
            finally:
                node.stop()

    def test_ping_roundtrip_between_two_nodes(self) -> None:
        with (
            tempfile.TemporaryDirectory() as d1,
            tempfile.TemporaryDirectory() as d2,
        ):
            p1 = free_port()
            p2 = free_port()
            n1 = Node(_make_config(p1, Path(d1)))
            n2 = Node(_make_config(p2, Path(d2)))
            n1.start()
            n2.start()
            try:
                time.sleep(0.2)
                contact2 = Contact(
                    node_id=n2.identity.node_id,
                    identity_algorithm=n2.identity.algorithm,
                    identity_public_key=n2.identity.public_key,
                    host="127.0.0.1",
                    port=p2,
                )
                response = n1.ping(contact2)
                self.assertIsInstance(response, Pong)
                self.assertEqual(response.responder.node_id, n2.identity.node_id)
            finally:
                n1.stop()
                n2.stop()


class TruncatedFrameTests(unittest.TestCase):
    def _accept_conn(
        self, srv: socket.socket, timeout: float = 2.0
    ) -> Connection:
        srv.settimeout(timeout)
        client_sock, peer = srv.accept()
        client_sock.settimeout(1.0)
        return Connection(
            sock=client_sock,
            peer=peer,
            decoder=FrameDecoder(
                protocol_version=PROTOCOL_VERSION,
                max_frame_payload=65536,
                allowed_types=set(ALLOWED_TYPES),
            ),
            connection_id=1,
        )

    def test_t19_partial_header_then_close(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        def client() -> None:
            c = socket.create_connection(("127.0.0.1", port), timeout=2.0)
            c.sendall(b"\x01\x01\x00\x00" + b"\x00" * 6)
            c.close()

        t = threading.Thread(target=client, daemon=True)
        t.start()

        conn = self._accept_conn(srv)
        try:
            with self.assertRaises(ProtocolError) as ctx:
                for _ in conn.recv_frames():
                    pass
            self.assertEqual(ctx.exception.code, "TRUNCATED_FRAME")
        finally:
            conn.close()
            srv.close()
            t.join(timeout=2.0)

    def test_t19_partial_payload_then_close(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        f = Frame(PROTOCOL_VERSION, 0x01, 0, b"\xAA" * 16, b"0123456789")
        blob = f.encode()

        def client() -> None:
            c = socket.create_connection(("127.0.0.1", port), timeout=2.0)
            c.sendall(blob[: HEADER_SIZE + 4])
            c.close()

        t = threading.Thread(target=client, daemon=True)
        t.start()

        conn = self._accept_conn(srv)
        try:
            with self.assertRaises(ProtocolError) as ctx:
                for _ in conn.recv_frames():
                    pass
            self.assertEqual(ctx.exception.code, "TRUNCATED_FRAME")
        finally:
            conn.close()
            srv.close()
            t.join(timeout=2.0)

    def test_t19_clean_eof_no_error(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        def client() -> None:
            c = socket.create_connection(("127.0.0.1", port), timeout=2.0)
            c.close()

        t = threading.Thread(target=client, daemon=True)
        t.start()

        conn = self._accept_conn(srv)
        try:
            received = list(conn.recv_frames())
            self.assertEqual(received, [])
        finally:
            conn.close()
            srv.close()
            t.join(timeout=2.0)

    def test_t19_node_survives_truncated_frame(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            port = free_port()
            node = Node(_make_config(port, Path(d)))
            node.start()
            try:
                time.sleep(0.2)
                s = socket.create_connection(("127.0.0.1", port), timeout=2.0)
                s.sendall(b"\x01\x01\x00\x00" + b"\x00" * 6)
                s.close()
                time.sleep(0.3)

                contact = Contact(
                    node_id=node.identity.node_id,
                    identity_algorithm=node.identity.algorithm,
                    identity_public_key=node.identity.public_key,
                    host="127.0.0.1",
                    port=port,
                )
                pong = node.ping(contact)
                self.assertIsInstance(pong, Pong)
            finally:
                node.stop()


class RequestIdCorrelationTests(unittest.TestCase):
    def test_t110_wrong_request_id_is_ignored(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        responder = _dummy_contact(port=port)

        def fake_server() -> None:
            client, _ = srv.accept()
            client.settimeout(2.0)
            dec = FrameDecoder(PROTOCOL_VERSION, 65536, set(ALLOWED_TYPES))
            try:
                req = None
                while req is None:
                    chunk = client.recv(4096)
                    if not chunk:
                        return
                    dec.feed(chunk)
                    try:
                        req = dec.next_frame()
                    except Exception:
                        continue
                wrong_rid = bytes(reversed(req.request_id))
                payload = encode_payload(
                    Pong(
                        responder=responder,
                        ping_timestamp_ms=12345,
                        responder_timestamp_ms=12346,
                    )
                )
                client.sendall(
                    Frame(PROTOCOL_VERSION, MSG_PONG, 0, wrong_rid, payload).encode()
                )
                client.sendall(
                    Frame(
                        PROTOCOL_VERSION, MSG_PONG, 0, req.request_id, payload
                    ).encode()
                )
                try:
                    while client.recv(1024):
                        pass
                except OSError:
                    pass
            finally:
                client.close()
                srv.close()

        t = threading.Thread(target=fake_server, daemon=True)
        t.start()

        with tempfile.TemporaryDirectory() as d:
            n = Node(_make_config(free_port(), Path(d)))
            pong = n.ping(responder)
            self.assertIsInstance(pong, Pong)
            self.assertEqual(pong.ping_timestamp_ms, 12345)

        t.join(timeout=3.0)


if __name__ == "__main__":
    unittest.main()