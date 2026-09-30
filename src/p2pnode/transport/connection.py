from __future__ import annotations

import logging
import socket
from dataclasses import dataclass, field
from typing import Iterator

from .framing import Frame, FrameDecoder, NeedMoreData, ProtocolError

log = logging.getLogger(__name__)

_CHUNK_SIZE = 4096


@dataclass
class Connection:
    sock: socket.socket
    peer: tuple[str, int]
    decoder: FrameDecoder
    connection_id: int
    _closed: bool = field(default=False, init=False)

    def recv_frames(self, max_frames: int | None = None) -> Iterator[Frame]:

        count = 0
        try:
            while True:
                while True:
                    try:
                        frame = self.decoder.next_frame()
                    except NeedMoreData:
                        break
                    except ProtocolError:
                        raise
                    yield frame
                    count += 1
                    if max_frames is not None and count >= max_frames:
                        return

                try:
                    chunk = self.sock.recv(_CHUNK_SIZE)
                except socket.timeout as exc:
                    raise ProtocolError("TIMEOUT", "read timeout") from exc
                if not chunk:
                    return
                self.decoder.feed(chunk)
        finally:
            self.close()

    def send_frame(self, frame: Frame) -> None:
        if self._closed:
            raise ProtocolError("CLOSED", "connection is closed")
        self.sock.sendall(frame.encode())

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    @property
    def closed(self) -> bool:
        return self._closed