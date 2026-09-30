from __future__ import annotations

import itertools
import logging
import socket
import threading
from typing import Callable

from .connection import Connection
from .framing import FrameDecoder

log = logging.getLogger(__name__)


class TCPServer:
    def __init__(
        self,
        host: str,
        port: int,
        protocol_version: int,
        max_frame_payload: int,
        allowed_types: set[int],
        on_connection: Callable[[Connection], None],
        read_timeout_ms: int,
    ) -> None:
        self._host = host
        self._port = port
        self._version = protocol_version
        self._max_payload = max_frame_payload
        self._allowed_types = allowed_types
        self._on_connection = on_connection
        self._read_timeout = read_timeout_ms / 1000.0

        self._sock: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._conn_ids = itertools.count(1)

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._host, self._port))
        sock.listen(64)
        self._sock = sock
        log.info("tcp server listening on %s:%d", self._host, self._port)

        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="tcp-accept", daemon=True
        )
        self._accept_thread.start()

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                client, peer = self._sock.accept()
            except OSError:
                return
            client.settimeout(self._read_timeout)
            conn = Connection(
                sock=client,
                peer=peer,
                decoder=FrameDecoder(
                    protocol_version=self._version,
                    max_frame_payload=self._max_payload,
                    allowed_types=self._allowed_types,
                ),
                connection_id=next(self._conn_ids),
            )
            log.info("incoming connection id=%d from %s:%d", conn.connection_id, *peer)
            threading.Thread(
                target=self._handle_safe,
                args=(conn,),
                name=f"conn-{conn.connection_id}",
                daemon=True,
            ).start()

    def _handle_safe(self, conn: Connection) -> None:
        try:
            self._on_connection(conn)
        except Exception:  # noqa: BLE001
            log.exception("connection id=%d handler crashed", conn.connection_id)
        finally:
            conn.close()

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2.0)