from __future__ import annotations

import unittest


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


def c(byte: int = 0) -> Contact:
    return Contact(node_id=bytes([byte]) * 32, host="127.0.0.1", port=9101)


class CodecTests(unittest.TestCase):
    def test_ping_roundtrip(self) -> None:
        msg = Ping(sender=c(1), timestamp_ms=1700000000000)
        decoded = decode_payload(MSG_PING, encode_payload(msg))
        self.assertEqual(decoded, msg)

    def test_pong_roundtrip(self) -> None:
        msg = Pong(responder=c(2), ping_timestamp_ms=1, responder_timestamp_ms=2)
        decoded = decode_payload(MSG_PONG, encode_payload(msg))
        self.assertEqual(decoded, msg)

    def test_find_node_request_roundtrip(self) -> None:
        msg = FindNodeRequest(sender=c(3), target_node_id=b"\xAA" * 32)
        decoded = decode_payload(MSG_FIND_NODE_REQUEST, encode_payload(msg))
        self.assertEqual(decoded, msg)

    def test_find_node_response_roundtrip(self) -> None:
        msg = FindNodeResponse(
            responder=c(4),
            target_node_id=b"\xBB" * 32,
            contacts=(c(5), c(6)),
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
        payload = (
            b'{"sender":{"node_id":"zz","host":"h","port":1},'
            b'"timestamp_ms":1}'
        )
        with self.assertRaises(PayloadError):
            decode_payload(MSG_PING, payload)

    def test_oversized_string_rejected(self) -> None:
        long_host = "h" * 5000
        payload = (
            '{"sender":{"node_id":"'
            + "00" * 32
            + '","host":"'
            + long_host
            + '","port":1},"timestamp_ms":1}'
        ).encode()
        with self.assertRaises(PayloadError):
            decode_payload(MSG_PING, payload)


if __name__ == "__main__":
    unittest.main()