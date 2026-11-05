from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..protocol.messages import Contact
from ..routing.lookup import LookupResult, lookup_node

if TYPE_CHECKING:
    from .node import Node

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BootstrapResult:

    success: bool
    bootstrap_contact: Contact | None
    self_lookup_result: LookupResult | None
    attempts: int


def parse_peer(peer: str) -> tuple[str, int]:
    if ":" not in peer:
        raise ValueError(f"invalid bootstrap peer: {peer!r} (expected host:port)")
    host, _, port_s = peer.rpartition(":")
    if not host or not port_s:
        raise ValueError(f"invalid bootstrap peer: {peer!r}")
    try:
        port = int(port_s)
    except ValueError as exc:
        raise ValueError(f"invalid port in bootstrap peer: {peer!r}") from exc
    if not (0 < port < 65536):
        raise ValueError(f"port out of range in bootstrap peer: {peer!r}")
    return host, port


def join_network(
    node: "Node",
    bootstrap_peers: list[str] | tuple[str, ...],
    self_lookup: bool = True,
) -> BootstrapResult:

    if not bootstrap_peers:
        log.info("bootstrap: no peers configured")
        return BootstrapResult(
            success=False,
            bootstrap_contact=None,
            self_lookup_result=None,
            attempts=0,
        )

    bootstrap_contact: Contact | None = None
    attempts = 0
    for peer in bootstrap_peers:
        attempts += 1
        try:
            host, port = parse_peer(peer)
        except ValueError as exc:
            log.warning("bootstrap: %s", exc)
            continue

        log.info("bootstrap: PING %s:%d", host, port)
        try:
            pong = node.ping_raw(host, port)
        except Exception as exc:  # noqa: BLE001
            log.warning("bootstrap: %s:%d failed: %s", host, port, exc)
            continue

        bootstrap_contact = pong.responder
        node.routing.add_or_update(
            bootstrap_contact, ping_lru=node._ping_lru
        )
        log.info(
            "bootstrap: joined via %s:%d node=%s",
            bootstrap_contact.host,
            bootstrap_contact.port,
            bootstrap_contact.node_id.hex()[:8],
        )
        break

    if bootstrap_contact is None:
        log.warning("bootstrap: all peers failed after %d attempts", attempts)
        return BootstrapResult(
            success=False,
            bootstrap_contact=None,
            self_lookup_result=None,
            attempts=attempts,
        )

    self_lookup_result: LookupResult | None = None
    if self_lookup:
        log.info("bootstrap: self-lookup for %s", node.identity.short_id)
        try:
            self_lookup_result = lookup_node(node, node.identity.node_id)
        except Exception:  # noqa: BLE001
            log.exception("bootstrap: self-lookup failed")

    return BootstrapResult(
        success=True,
        bootstrap_contact=bootstrap_contact,
        self_lookup_result=self_lookup_result,
        attempts=attempts,
    )