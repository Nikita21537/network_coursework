from __future__ import annotations

import unittest

from p2pnode.protocol.codec import encode_payload
from p2pnode.protocol.constants import (
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
from p2pnode.rpc.dispatcher import Dispatcher
from p2pnode.transport.framing import Frame


def c(byte: int = 0) -> Contact:
    return Contact(node_id=bytes([byte]) * 32, host="127.0.0.1", port=9101)


class DispatcherTests(unittest.TestCase):
    def _dispatcher(self) -> Dispatcher:
        d = Dispatcher()
        d.register(MSG_PING, MSG_PONG, lambda m: Pong(
            responder=c(9),
            ping_timestamp_ms=m.timestamp_ms,
            responder_timestamp_ms=0,
        ))
        d.register(
            MSG_FIND_NODE_REQUEST,
            MSG_FIND_NODE_RESPONSE,
            lambda m: FindNodeResponse(
                responder=c(9), target_node_id=m.target_node_id, contacts=()
            ),
        )
        return d

    def test_ping_response_type(self) -> None:
        d = self._dispatcher()
        self.assertEqual(d.response_type_for(MSG_PING), MSG_PONG)

    def test_dispatch_ping(self) -> None:
        d = self._dispatcher()
        msg = Ping(sender=c(1), timestamp_ms=123)
        frame = Frame(1, MSG_PING, 0, b"\x00" * 16, encode_payload(msg))
        result = d.dispatch(frame)
        self.assertIsInstance(result, Pong)
        self.assertEqual(result.ping_timestamp_ms, 123)

    def test_dispatch_find_node(self) -> None:
        d = self._dispatcher()
        msg = FindNodeRequest(sender=c(1), target_node_id=b"\x11" * 32)
        frame = Frame(1, MSG_FIND_NODE_REQUEST, 0, b"\x00" * 16, encode_payload(msg))
        result = d.dispatch(frame)
        self.assertIsInstance(result, FindNodeResponse)

    def test_dispatch_bad_payload(self) -> None:
        d = self._dispatcher()
        frame = Frame(1, MSG_PING, 0, b"\x00" * 16, b"not-json")
        result = d.dispatch(frame)
        self.assertIsInstance(result, ErrorMessage)
        self.assertEqual(result.code, "BAD_PAYLOAD")

    def test_response_types_not_dispatched(self) -> None:
        d = self._dispatcher()
        frame = Frame(1, MSG_PONG, 0, b"\x00" * 16, b"{}")
        self.assertIsNone(d.dispatch(frame))


if __name__ == "__main__":
    unittest.main()