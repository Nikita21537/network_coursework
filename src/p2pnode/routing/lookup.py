from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..protocol.messages import Contact, FindNodeResponse
from .contact import xor_distance

if TYPE_CHECKING:
    from ..node.node import Node

log = logging.getLogger(__name__)


DEFAULT_ALPHA = 3


@dataclass(frozen=True)
class LookupResult:

    lookup_id: str
    target_node_id: bytes
    closest_contacts: tuple[Contact, ...]
    success: bool
    rpc_count: int
    iterations: int
    timeouts: tuple[bytes, ...]
    duration_ms: int


def _log(msg: str, *args, **kwargs) -> None:
    log.info(msg, *args, **kwargs)


def lookup_node(
    node: "Node",
    target_node_id: bytes,
    alpha: int = DEFAULT_ALPHA,
) -> LookupResult:

    if len(target_node_id) != 32:
        raise ValueError("target_node_id must be 32 bytes")
    if alpha <= 0:
        raise ValueError("alpha must be > 0")

    k = node.config.k_bucket_size
    started = time.monotonic()
    lookup_id = uuid.uuid4().hex[:8]

    log.info(
        "lookup start id=%s target=%s k=%d alpha=%d",
        lookup_id,
        target_node_id.hex()[:8],
        k,
        alpha,
    )


    initial = node.routing.find_closest(target_node_id, limit=k)
    shortlist: dict[bytes, Contact] = {c.node_id: c for c in initial}
    asked: set[bytes] = set()
    timeouts: list[bytes] = []
    rpc_count = 0
    iterations = 0

    target_int = int.from_bytes(target_node_id, "big")

    def _sorted_shortlist() -> list[Contact]:
        return sorted(
            shortlist.values(),
            key=lambda c: xor_distance(c.node_id, target_int),
        )

    while True:
        sorted_candidates = _sorted_shortlist()


        k_closest = sorted_candidates[:k]
        if k_closest and all(c.node_id in asked for c in k_closest):
            log.info(
                "lookup %s stop: all %d closest already asked",
                lookup_id,
                k,
            )
            break


        to_ask = [
            c for c in sorted_candidates if c.node_id not in asked
        ][:alpha]
        if not to_ask:
            log.info("lookup %s stop: no unasked candidates left", lookup_id)
            break

        iterations += 1
        log.info(
            "lookup %s iter=%d asking %d candidates: %s",
            lookup_id,
            iterations,
            len(to_ask),
            [c.node_id.hex()[:8] for c in to_ask],
        )


        with ThreadPoolExecutor(max_workers=len(to_ask)) as pool:
            future_to_contact = {
                pool.submit(node.find_node, c, target_node_id): c
                for c in to_ask
            }
            for fut in as_completed(future_to_contact):
                c = future_to_contact[fut]
                asked.add(c.node_id)
                rpc_count += 1
                try:
                    response = fut.result()
                except Exception as exc:

                    log.warning(
                        "lookup %s: FIND_NODE to %s failed: %s",
                        lookup_id,
                        c.node_id.hex()[:8],
                        exc,
                    )
                    timeouts.append(c.node_id)
                    continue
                assert isinstance(response, FindNodeResponse)

                shortlist.setdefault(response.responder.node_id, response.responder)

                for new_contact in response.contacts:
                    if new_contact.node_id == node.identity.node_id:
                        continue
                    if new_contact.node_id == target_node_id:

                        shortlist[new_contact.node_id] = new_contact
                        continue
                    if new_contact.node_id in shortlist:
                        continue
                    shortlist[new_contact.node_id] = new_contact


    final_sorted = _sorted_shortlist()[:k]
    duration_ms = int((time.monotonic() - started) * 1000)
    success = any(c.node_id == target_node_id for c in final_sorted)

    result = LookupResult(
        lookup_id=lookup_id,
        target_node_id=target_node_id,
        closest_contacts=tuple(final_sorted),
        success=success,
        rpc_count=rpc_count,
        iterations=iterations,
        timeouts=tuple(timeouts),
        duration_ms=duration_ms,
    )
    log.info(
        "lookup %s done: success=%s contacts=%d rpc=%d iters=%d "
        "timeouts=%d duration_ms=%d",
        lookup_id,
        success,
        len(final_sorted),
        rpc_count,
        iterations,
        len(timeouts),
        duration_ms,
    )
    return result