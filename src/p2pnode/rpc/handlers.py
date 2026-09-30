from __future__ import annotations

import logging
import time

from ..protocol.messages import (
    FindNodeRequest,
    FindNodeResponse,
    Ping,
    Pong,
)

log = logging.getLogger(__name__)


class PingHandler:
    def __init__(self, node) -> None:  # noqa: ANN001
        self._node = node

    def __call__(self, message: object) -> Pong:
        assert isinstance(message, Ping)
        log.info(
            "PING from %s:%d node=%s",
            message.sender.host,
            message.sender.port,
            message.sender.node_id.hex()[:8],
        )
        return Pong(
            responder=self._node.local_contact(),
            ping_timestamp_ms=message.timestamp_ms,
            responder_timestamp_ms=int(time.time() * 1000),
        )


class FindNodeHandler:
    def __init__(self, node) -> None:  # noqa: ANN001
        self._node = node

    def __call__(self, message: object) -> FindNodeResponse:
        assert isinstance(message, FindNodeRequest)
        log.info(
            "FIND_NODE target=%s from %s:%d",
            message.target_node_id.hex()[:8],
            message.sender.host,
            message.sender.port,
        )
        # Этап 1: k-bucket ещё нет, возвращаем пустой список.
        return FindNodeResponse(
            responder=self._node.local_contact(),
            target_node_id=message.target_node_id,
            contacts=(),
        )