from __future__ import annotations

import logging
from typing import Callable

from ..protocol.codec import PayloadError, decode_payload
from ..protocol.constants import (
    MSG_ERROR,
    MSG_FIND_NODE_REQUEST,
    MSG_FIND_NODE_RESPONSE,
    MSG_PING,
    MSG_PONG,
)
from ..protocol.messages import ErrorMessage
from ..transport.framing import Frame

log = logging.getLogger(__name__)

Handler = Callable[[object], object | None]


class Dispatcher:
    def __init__(self) -> None:
        self._handlers: dict[int, Handler] = {}
        self._responses: dict[int, int] = {}

    def register(self, request_type: int, response_type: int, handler: Handler) -> None:
        self._handlers[request_type] = handler
        self._responses[request_type] = response_type

    def response_type_for(self, request_type: int) -> int | None:
        return self._responses.get(request_type)

    def dispatch(self, frame: Frame) -> object | None:
        if frame.type in (MSG_PONG, MSG_FIND_NODE_RESPONSE, MSG_ERROR):
            # Ответы обрабатываются вызывающей стороной RPC, не диспетчером.
            return None
        handler = self._handlers.get(frame.type)
        if handler is None:
            log.warning("no handler for type=0x%02X", frame.type)
            return ErrorMessage(code="BAD_TYPE", message=f"no handler for {frame.type}")
        try:
            message = decode_payload(frame.type, frame.payload)
        except PayloadError as exc:
            log.warning("payload decode failed: %s", exc)
            return ErrorMessage(code="BAD_PAYLOAD", message=str(exc))
        try:
            return handler(message)
        except Exception:  # noqa: BLE001
            log.exception("handler crashed for type=0x%02X", frame.type)
            return ErrorMessage(code="INTERNAL", message="handler error")


def default_dispatcher(node) -> Dispatcher:  # noqa: ANN001
    from .handlers import FindNodeHandler, PingHandler

    d = Dispatcher()
    d.register(MSG_PING, MSG_PONG, PingHandler(node))
    d.register(
        MSG_FIND_NODE_REQUEST, MSG_FIND_NODE_RESPONSE, FindNodeHandler(node)
    )
    return d