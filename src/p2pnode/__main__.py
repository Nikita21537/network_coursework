from __future__ import annotations

import argparse
import dataclasses
import logging
import signal
import sys
import time
from pathlib import Path


from .config import Config
from .logging_setup import setup_logging
from .node.node import Node


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="p2pnode",
        description="Защищённая оверлейная P2P-сеть — узел",
    )
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", type=str, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    cfg = Config.load(args.config)
    overrides: dict = {}
    if args.port is not None:
        overrides["listen_port"] = args.port
    if args.host is not None:
        overrides["listen_host"] = args.host
    if overrides:
        cfg = dataclasses.replace(cfg, **overrides)

    logs_dir = Path(cfg.node_state_dir) / "logs"
    setup_logging(cfg.log_level, logs_dir)
    log = logging.getLogger("main")

    log.info(
        "starting node state_dir=%s listen=%s:%d",
        cfg.node_state_dir,
        cfg.listen_host,
        cfg.listen_port,
    )

    node = Node(cfg)
    node.start()

    # Bootstrap: подключаемся к сети, если указаны peers.
    if cfg.bootstrap_peers:
        log.info(
            "bootstrap peers configured: %s", list(cfg.bootstrap_peers)
        )
        try:
            result = node.join(cfg.bootstrap_peers)
            log.info(
                "bootstrap result: success=%s attempts=%d bootstrap_node=%s "
                "routing_size=%d",
                result.success,
                result.attempts,
                result.bootstrap_contact.node_id.hex()[:8]
                if result.bootstrap_contact
                else "none",
                len(node.routing),
            )
            if result.self_lookup_result is not None:
                r = result.self_lookup_result
                log.info(
                    "bootstrap self-lookup: success=%s contacts=%d "
                    "rpc=%d iters=%d duration_ms=%d",
                    r.success,
                    len(r.closest_contacts),
                    r.rpc_count,
                    r.iterations,
                    r.duration_ms,
                )
        except Exception:  # noqa: BLE001
            log.exception(
                "bootstrap failed; continuing as a standalone node"
            )

    stopped = {"flag": False}

    def _on_signal(signum, _frame):  # noqa: ANN001
        if stopped["flag"]:
            return
        stopped["flag"] = True
        log.info("signal %d received, shutting down", signum)
        try:
            node.stop()
        finally:
            log.info("node stopped")

    signal.signal(signal.SIGINT, _on_signal)

    if hasattr(signal, "SIGTERM"):
        try:
            signal.signal(signal.SIGTERM, _on_signal)
        except (AttributeError, ValueError):
            log.warning("SIGTERM handler could not be installed")

    if hasattr(signal, "SIGBREAK"):
        try:
            signal.signal(signal.SIGBREAK, _on_signal)
        except (AttributeError, ValueError):
            log.warning("SIGBREAK handler could not be installed")

    try:
        while not stopped["flag"]:
            time.sleep(0.5)
    except KeyboardInterrupt:
        _on_signal(signal.SIGINT, None)

    return 0


if __name__ == "__main__":
    sys.exit(main())