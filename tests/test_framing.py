from __future__ import annotations

import os
import unittest


from p2pnode.protocol.constants import ALLOWED_TYPES, PROTOCOL_VERSION
from p2pnode.transport.framing import (
    HEADER_SIZE,
    Frame,
    FrameDecoder,
    NeedMoreData,
    ProtocolError,
)


def make_decoder(max_payload: int = 65536) -> FrameDecoder:
    return FrameDecoder(
        protocol_version=PROTOCOL_VERSION,
        max_frame_payload=max_payload,
        allowed_types=set(ALLOWED_TYPES),
    )


class FramingTests(unittest.TestCase):
    def test_t11_encode_decode_roundtrip(self) -> None:
        frame = Frame(
            version=PROTOCOL_VERSION,
            type=0x01,
            flags=0,
            request_id=os.urandom(16),
            payload=b"hello",
        )
        decoder = make_decoder()
        decoder.feed(frame.encode())
        decoded = decoder.next_frame()
        self.assertEqual(decoded.version, frame.version)
        self.assertEqual(decoded.type, frame.type)
        self.assertEqual(decoded.flags, frame.flags)
        self.assertEqual(decoded.request_id, frame.request_id)
        self.assertEqual(decoded.payload, frame.payload)

    def test_t12_partial_header(self) -> None:
        frame = Frame(PROTOCOL_VERSION, 0x01, 0, os.urandom(16), b"x")
        data = frame.encode()
        decoder = make_decoder()
        decoder.feed(data[: HEADER_SIZE - 1])
        with self.assertRaises(NeedMoreData):
            decoder.next_frame()

    def test_t13_partial_payload(self) -> None:
        frame = Frame(PROTOCOL_VERSION, 0x01, 0, os.urandom(16), b"abcdef")
        data = frame.encode()
        decoder = make_decoder()
        decoder.feed(data[: HEADER_SIZE + 3])
        with self.assertRaises(NeedMoreData):
            decoder.next_frame()
        decoder.feed(data[HEADER_SIZE + 3 :])
        decoded = decoder.next_frame()
        self.assertEqual(decoded.payload, b"abcdef")

    def test_t14_two_frames_in_one_read(self) -> None:
        rid = os.urandom(16)
        f1 = Frame(PROTOCOL_VERSION, 0x01, 0, rid, b"a")
        f2 = Frame(PROTOCOL_VERSION, 0x02, 0, rid, b"bb")
        decoder = make_decoder()
        decoder.feed(f1.encode() + f2.encode())
        self.assertEqual(decoder.next_frame().payload, b"a")
        self.assertEqual(decoder.next_frame().payload, b"bb")

    def test_t15_random_splitting(self) -> None:
        import random

        random.seed(42)
        rid = os.urandom(16)
        frames = [
            Frame(PROTOCOL_VERSION, 0x01, 0, rid, bytes([i]) * (i % 50))
            for i in range(100)
        ]
        stream = b"".join(f.encode() for f in frames)
        decoder = make_decoder()
        out = []
        i = 0
        while i < len(stream):
            step = random.randint(1, 17)
            decoder.feed(stream[i : i + step])
            i += step
            while True:
                try:
                    out.append(decoder.next_frame())
                except NeedMoreData:
                    break
        self.assertEqual(len(out), 100)
        for original, decoded in zip(frames, out):
            self.assertEqual(original.payload, decoded.payload)

    def test_t16_payload_length_exceeds_max(self) -> None:
        # Собираем заголовок с завышенной длиной вручную.
        import struct

        header = struct.pack(">BBH16sI", PROTOCOL_VERSION, 0x01, 0, os.urandom(16), 65537)
        decoder = make_decoder(max_payload=65536)
        decoder.feed(header)
        with self.assertRaises(ProtocolError) as ctx:
            decoder.next_frame()
        self.assertEqual(ctx.exception.code, "BAD_LENGTH")

    def test_t17_unknown_version(self) -> None:
        import struct

        header = struct.pack(">BBH16sI", 99, 0x01, 0, os.urandom(16), 0)
        decoder = make_decoder()
        decoder.feed(header)
        with self.assertRaises(ProtocolError) as ctx:
            decoder.next_frame()
        self.assertEqual(ctx.exception.code, "BAD_VERSION")

    def test_t18_unknown_type(self) -> None:
        import struct

        header = struct.pack(">BBH16sI", PROTOCOL_VERSION, 0x55, 0, os.urandom(16), 0)
        decoder = make_decoder()
        decoder.feed(header)
        with self.assertRaises(ProtocolError) as ctx:
            decoder.next_frame()
        self.assertEqual(ctx.exception.code, "BAD_TYPE")

    def test_t19_truncated_stream_no_partial_frame(self) -> None:
        frame = Frame(PROTOCOL_VERSION, 0x01, 0, os.urandom(16), b"payload")
        decoder = make_decoder()
        decoder.feed(frame.encode()[: HEADER_SIZE + 2])
        with self.assertRaises(NeedMoreData):
            decoder.next_frame()
        # Буфер не содержит частично собранного сообщения.
        self.assertTrue(decoder.has_buffered_data())


if __name__ == "__main__":
    unittest.main()