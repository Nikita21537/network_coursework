from __future__ import annotations

import logging
import secrets
import socket
import threading
import time

from ..config import Config
from ..identity.node_id import Identity
from ..protocol.constants import ALLOWED_TYPES, MSG_PING
from ..protocol.messages import Contact, ErrorMessage, Ping
from ..rpc.dispatcher import Dispatcher, default_dispatcher
from ..transport.connection import Connection
from ..transport.framing import Frame, FrameDecoder, ProtocolError
from ..transport.server import TCPServer

log = logging.getLogger(__name__)


class RpcError(Exception):
    pass


class Node:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.identity = Identity.load_or_create(config.node_state_dir)
        self.dispatcher: Dispatcher = default_dispatcher(self)
        self.server = TCPServer(
            host=config.listen_host,
            port=config.listen_port,
            protocol_version=config.protocol_version,
            max_frame_payload=config.max_frame_payload,
            allowed_types=set(ALLOWED_TYPES),
            on_connection=self._on_connection,
            read_timeout_ms=config.read_timeout_ms,
        )
        self._serving = threading.Event()

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------
    def start(self) -> None:
        self.server.start()
        log.info(
            "node started id=%s listen=%s:%d",
            self.identity.short_id,
            self.config.listen_host,
            self.config.listen_port,
        )

    def serve_forever(self) -> None:
        self._serving.wait()

    def stop(self) -> None:
        log.info("stopping node %s", self.identity.short_id)
        self.server.stop()
        self._serving.set()

    def local_contact(self) -> Contact:
        host = self.config.listen_host
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        return Contact(
            node_id=self.identity.node_id,
            host=host,
            port=self.config.listen_port,
        )

    # ------------------------------------------------------------------
    # Входящие соединения
    # ------------------------------------------------------------------
    def _on_connection(self, conn: Connection) -> None:
        try:
            for frame in conn.recv_frames():
                self._handle_frame(conn, frame)
        except ProtocolError as exc:
            log.warning(
                "connection id=%d protocol error: %s (%s)",
                conn.connection_id,
                exc.code,
                exc.message,
            )
            self._try_send_error(conn, frame=None, code=exc.code, message=exc.message)
        except Exception:  # noqa: BLE001
            log.exception("connection id=%d failed", conn.connection_id)
        finally:
            log.info("connection id=%d closed", conn.connection_id)

    def _handle_frame(self, conn: Connection, frame: Frame) -> None:
        log.info(
            "recv type=0x%02X request_id=%s len=%d",
            frame.type,
            frame.request_id.hex()[:8],
            len(frame.payload),
        )
        response = self.dispatcher.dispatch(frame)
        if response is None:
            return
        response_type = self.dispatcher.response_type_for(frame.type)
        if response_type is None:
            log.warning("no response type for request type=0x%02X", frame.type)
            return
        from ..protocol.codec import PayloadError, encode_payload

        try:
            payload = encode_payload(response)
        except PayloadError as exc:
            log.error("failed to encode response: %s", exc)
            return
        out = Frame(
            version=self.config.protocol_version,
            type=response_type,
            flags=0,
            request_id=frame.request_id,
            payload=payload,
        )
        conn.send_frame(out)
        log.info(
            "sent type=0x%02X request_id=%s len=%d",
            out.type,
            out.request_id.hex()[:8],
            len(out.payload),
        )

    def _try_send_error(
        self,
        conn: Connection,
        frame: Frame | None,
        code: str,
        message: str,
    ) -> None:
        if conn.closed:
            return
        request_id = frame.request_id if frame is not None else b"\x00" * 16
        from ..protocol.codec import encode_payload

        try:
            payload = encode_payload(ErrorMessage(code=code, message=message))
            out = Frame(
                version=self.config.protocol_version,
                type=0x7F,
                flags=0,
                request_id=request_id,
                payload=payload,
            )
            conn.send_frame(out)
        except Exception:  # noqa: BLE001
            log.debug("could not send ERROR frame", exc_info=True)

    # ------------------------------------------------------------------
    # Исходящие RPC
    # ------------------------------------------------------------------
    def send_request(
        self,
        contact: Contact,
        message: object,
        timeout_ms: int | None = None,
    ) -> object:
        from ..protocol.codec import PayloadError, decode_payload, encode_payload

        timeout_ms = timeout_ms or self.config.read_timeout_ms
        message_type = self._message_type(message)
        request_id = secrets.token_bytes(16)
        payload = encode_payload(message)
        frame = Frame(
            version=self.config.protocol_version,
            type=message_type,
            flags=0,
            request_id=request_id,
            payload=payload,
        )

        try:
            sock = socket.create_connection(
                (contact.host, contact.port),
                timeout=self.config.connect_timeout_ms / 1000.0,
            )
        except OSError as exc:
            raise RpcError(f"connect failed: {exc}") from exc

        sock.settimeout(timeout_ms / 1000.0)
        conn = Connection(
            sock=sock,
            peer=(contact.host, contact.port),
            decoder=FrameDecoder(
                protocol_version=self.config.protocol_version,
                max_frame_payload=self.config.max_frame_payload,
                allowed_types=set(ALLOWED_TYPES),
            ),
            connection_id=0,
        )
        try:
            conn.send_frame(frame)
            log.info(
                "sent request type=0x%02X request_id=%s",
                message_type,
                request_id.hex()[:8],
            )
            for resp in conn.recv_frames():
                if resp.request_id != request_id:
                    log.warning(
                        "ignoring response with unexpected request_id=%s",
                        resp.request_id.hex()[:8],
                    )
                    continue
                log.info(
                    "recv response type=0x%02X request_id=%s",
                    resp.type,
                    resp.request_id.hex()[:8],
                )
                return decode_payload(resp.type, resp.payload)
            raise RpcError("connection closed before response")
        except ProtocolError as exc:
            raise RpcError(f"protocol error: {exc.code} {exc.message}") from exc
        finally:
            conn.close()

    @staticmethod
    def _message_type(message: object) -> int:
        from ..protocol.messages import (
            FindNodeRequest,
            Ping,
        )

        if isinstance(message, Ping):
            return 0x01
        if isinstance(message, FindNodeRequest):
            return 0x03
        raise ValueError(f"unsupported request message: {type(message).__name__}")

    def ping(self, contact: Contact) -> object:
        msg = Ping(
            sender=self.local_contact(),
            timestamp_ms=int(time.time() * 1000),
        )
        return self.send_request(contact, msg, timeout_ms=self.config.ping_timeout_ms)