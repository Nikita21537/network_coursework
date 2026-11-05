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
        try:
            result = self._node.routing.add_or_update(
                message.sender, ping_lru=self._node._ping_lru
            )
            log.info(
                "routing add_or_update from PING: added=%s updated=%s "
                "rejected_self=%s rejected_full_alive=%s bucket=%d",
                result.added,
                result.updated,
                result.rejected_self,
                result.rejected_full_alive,
                result.bucket_index,
            )
        except Exception:  # noqa: BLE001
            log.exception("routing add_or_update failed; continuing with PONG")

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


        try:
            result = self._node.routing.add_or_update(
                message.sender, ping_lru=self._node._ping_lru
            )
            log.info(
                "routing add_or_update from FIND_NODE: added=%s updated=%s "
                "rejected_self=%s rejected_full_alive=%s bucket=%d",
                result.added,
                result.updated,
                result.rejected_self,
                result.rejected_full_alive,
                result.bucket_index,
            )
        except Exception:  # noqa: BLE001
            log.exception("routing add_or_update failed; continuing")


        k = self._node.config.k_bucket_size
        contacts = self._node.routing.find_closest(
            message.target_node_id, limit=k
        )
        log.info(
            "FIND_NODE response: target=%s contacts=%d",
            message.target_node_id.hex()[:8],
            len(contacts),
        )

        return FindNodeResponse(
            responder=self._node.local_contact(),
            target_node_id=message.target_node_id,
            contacts=tuple(contacts),
        )