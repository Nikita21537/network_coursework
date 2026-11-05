from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from p2pnode.identity import Identity
from p2pnode.protocol.codec import PayloadError, decode_payload, encode_payload
from p2pnode.protocol.constants import (
    MSG_ERROR,
    MSG_FIND_NODE_REQUEST,
    MSG_FIND_NODE_RESPONSE,
    MSG_PING,
    MSG_PONG,
)
from p2pnode.protocol.messages import (
    Contact,
    ErrorMessage,
    FindNodeRequest,
    FindNodeResponse,
    Ping,
    Pong,
)


def make_contact(host: str = "127.0.0.1", port: int = 9101) -> Contact:
    with tempfile.TemporaryDirectory() as d:
        ident = Identity.load_or_create(Path(d))
        return Contact(
            node_id=ident.node_id,
            identity_algorithm=ident.algorithm,
            identity_public_key=ident.public_key,
            host=host,
            port=port,
        )


def c(byte: int = 0) -> Contact:  # сохраняем сигнатуру для обратной совместимости тестов
    return make_contact()


class CodecTests(unittest.TestCase):
    def test_ping_roundtrip(self) -> None:
        msg = Ping(sender=c(), timestamp_ms=1700000000000)
        decoded = decode_payload(MSG_PING, encode_payload(msg))
        self.assertEqual(decoded, msg)

    def test_pong_roundtrip(self) -> None:
        msg = Pong(
            responder=c(), ping_timestamp_ms=1, responder_timestamp_ms=2
        )
        decoded = decode_payload(MSG_PONG, encode_payload(msg))
        self.assertEqual(decoded, msg)

    def test_find_node_request_roundtrip(self) -> None:
        msg = FindNodeRequest(sender=c(), target_node_id=b"\xAA" * 32)
        decoded = decode_payload(MSG_FIND_NODE_REQUEST, encode_payload(msg))
        self.assertEqual(decoded, msg)

    def test_find_node_response_roundtrip(self) -> None:
        msg = FindNodeResponse(
            responder=c(),
            target_node_id=b"\xBB" * 32,
            contacts=(c(), c()),
        )
        decoded = decode_payload(MSG_FIND_NODE_RESPONSE, encode_payload(msg))
        self.assertEqual(decoded, msg)

    def test_error_roundtrip(self) -> None:
        msg = ErrorMessage(code="BAD_LENGTH", message="too big")
        decoded = decode_payload(MSG_ERROR, encode_payload(msg))
        self.assertEqual(decoded, msg)

    def test_missing_field_rejected(self) -> None:
        with self.assertRaises(PayloadError):
            decode_payload(MSG_PING, b'{"timestamp_ms": 1}')

    def test_wrong_type_rejected(self) -> None:
        with self.assertRaises(PayloadError):
            decode_payload(MSG_PING, b'{"sender": "x", "timestamp_ms": 1}')

    def test_bad_hex_rejected(self) -> None:
        # sender с плохим hex в identity_public_key
        payload = (
            b'{"sender":{"node_id":"' + b"00" * 32
            + b'","identity_algorithm":"ed25519",'
            + b'"identity_public_key":"zz","host":"h","port":1},'
            + b'"timestamp_ms":1}'
        )
        with self.assertRaises(PayloadError):
            decode_payload(MSG_PING, payload)

    def test_oversized_string_rejected(self) -> None:
        long_host = "h" * 5000
        with tempfile.TemporaryDirectory() as d:
            ident = Identity.load_or_create(Path(d))
        payload = (
            '{"sender":{"node_id":"'
            + ident.node_id.hex()
            + '","identity_algorithm":"ed25519",'
            + '"identity_public_key":"'
            + ident.public_key.hex()
            + '","host":"'
            + long_host
            + '","port":1},"timestamp_ms":1}'
        ).encode()
        with self.assertRaises(PayloadError):
            decode_payload(MSG_PING, payload)


if __name__ == "__main__":
    unittest.main()