from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_ROOT = ROOT / "state"
LOGS_ROOT = ROOT / "logs"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_for_port(port: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def start_node(name: str, port: int) -> subprocess.Popen:
    state = STATE_ROOT / name
    state.mkdir(parents=True, exist_ok=True)
    cfg = STATE_ROOT / f"{name}.env"
    cfg.write_text(
        "\n".join(
            [
                f"NODE_STATE_DIR={state}",
                "LISTEN_HOST=127.0.0.1",
                f"LISTEN_PORT={port}",
                "BOOTSTRAP_PEERS=",
                "K_BUCKET_SIZE=3",
                "ALPHA=3",
                "CONNECT_TIMEOUT_MS=1000",
                "READ_TIMEOUT_MS=2000",
                "PING_TIMEOUT_MS=1000",
                "MAX_FRAME_PAYLOAD=65536",
                "LOG_LEVEL=INFO",
                "",
            ]
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(ROOT / "src")
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [sys.executable, "-m", "p2pnode", "--config", str(cfg)],
        cwd=ROOT,
        env=env,
        **kwargs,
    )
    print(f"[demo] {name} pid={proc.pid} port={port}")
    return proc


def main() -> int:
    STATE_ROOT.mkdir(exist_ok=True)
    LOGS_ROOT.mkdir(exist_ok=True)

    names = ["n1", "n2", "n3", "n4", "n5"]
    ports = [free_port() for _ in names]
    procs = [start_node(name, port) for name, port in zip(names, ports)]

    try:
        for name, port in zip(names, ports):
            if not wait_for_port(port):
                print(f"ERROR: {name} did not start")
                return 1
        print("[demo] all 5 nodes are listening")
        time.sleep(1.0)


        from p2pnode.config import Config
        from p2pnode.node.node import Node
        from p2pnode.protocol.messages import Contact
        from p2pnode.routing.lookup import lookup_node

        with tempfile_or_skip():

            # bootstrap n1 и lookup n5.
            client_state = STATE_ROOT / "client"
            client_state.mkdir(exist_ok=True)
            client = Node(
                Config(
                    node_state_dir=client_state,
                    listen_host="127.0.0.1",
                    listen_port=free_port(),
                    bootstrap_peers=(),
                    node_id_bits=256,
                    k_bucket_size=3,
                    alpha=3,
                    connect_timeout_ms=1000,
                    read_timeout_ms=2000,
                    ping_timeout_ms=1000,
                    max_frame_payload=65536,
                    protocol_version=1,
                    log_level="INFO",
                )
            )

            print("[demo] lookup demo will be enabled after step 8 (bootstrap)")
            return 0
    finally:
        print("[demo] stopping nodes...")
        for p in procs:
            if os.name == "nt":
                try:
                    p.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:  # noqa: BLE001
                    p.kill()
            else:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        print("[demo] done")


def tempfile_or_skip():
    import tempfile

    return tempfile.TemporaryDirectory()


if __name__ == "__main__":
    sys.exit(main())