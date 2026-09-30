

from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER_SIZE = 24
_HEADER_STRUCT = struct.Struct(">BBH16sI")


class ProtocolError(Exception):


    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NeedMoreData(Exception):
    """Недостаточно байтов для полного кадра."""


@dataclass(frozen=True)
class Frame:
    version: int
    type: int
    flags: int
    request_id: bytes
    payload: bytes

    def encode(self) -> bytes:
        header = _HEADER_STRUCT.pack(
            self.version,
            self.type,
            self.flags,
            self.request_id,
            len(self.payload),
        )
        return header + self.payload


class FrameDecoder:


    def __init__(
        self,
        protocol_version: int,
        max_frame_payload: int,
        allowed_types: set[int],
    ) -> None:
        self._version = protocol_version
        self._max_payload = max_frame_payload
        self._allowed_types = allowed_types
        self._buffer = bytearray()

    def feed(self, data: bytes) -> None:
        if data:
            self._buffer.extend(data)

    def next_frame(self) -> Frame:

        if len(self._buffer) < HEADER_SIZE:
            raise NeedMoreData()

        version, mtype, flags, request_id, payload_length = _HEADER_STRUCT.unpack_from(
            self._buffer, 0
        )

        if version != self._version:
            raise ProtocolError("BAD_VERSION", f"unsupported version {version}")
        if mtype not in self._allowed_types:
            raise ProtocolError("BAD_TYPE", f"unknown message type {mtype}")
        if payload_length > self._max_payload:
            # Отклоняем до выделения буфера.
            raise ProtocolError(
                "BAD_LENGTH",
                f"payload_length {payload_length} exceeds {self._max_payload}",
            )

        total = HEADER_SIZE + payload_length
        if len(self._buffer) < total:
            raise NeedMoreData()

        payload = bytes(self._buffer[HEADER_SIZE:total])
        del self._buffer[:total]
        return Frame(
            version=version,
            type=mtype,
            flags=flags,
            request_id=request_id,
            payload=payload,
        )

    def has_buffered_data(self) -> bool:
        return bool(self._buffer)