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


def start_node(name: str, port: int, bootstrap: list[str]) -> subprocess.Popen:
    state = STATE_ROOT / name
    state.mkdir(parents=True, exist_ok=True)
    cfg = STATE_ROOT / f"{name}.env"
    cfg.write_text(
        "\n".join(
            [
                f"NODE_STATE_DIR={state}",
                "LISTEN_HOST=127.0.0.1",
                f"LISTEN_PORT={port}",
                f"BOOTSTRAP_PEERS={','.join(bootstrap)}",
                "K_BUCKET_SIZE=3",
                "ALPHA=3",
                "CONNECT_TIMEOUT_MS=2000",
                "READ_TIMEOUT_MS=3000",
                "PING_TIMEOUT_MS=3000",
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
    print(f"[demo] {name} pid={proc.pid} port={port} bootstrap={bootstrap}")
    return proc


def stop_all(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        if p.poll() is None:
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


def run_scheme(scheme: str) -> int:
    print(f"\n=== bootstrap scheme: {scheme} ===")
    names = ["seed", "n2", "n3", "n4", "n5"]
    ports = [free_port() for _ in names]
    procs: list[subprocess.Popen] = []

    try:
        # 1. Запуск seed без bootstrap.
        procs.append(start_node("seed", ports[0], []))
        if not wait_for_port(ports[0]):
            print("ERROR: seed did not start")
            return 1

        # 2. Запуск остальных.
        for i in range(1, 5):
            name = f"{scheme}-{names[i]}"
            if scheme == "star":
                bootstrap = [f"127.0.0.1:{ports[0]}"]
            elif scheme == "ring":
                bootstrap = [f"127.0.0.1:{ports[i - 1]}"]
            else:
                raise ValueError(scheme)
            procs.append(start_node(name, ports[i], bootstrap))
            if not wait_for_port(ports[i]):
                print(f"ERROR: {name} did not start")
                return 1

        print(f"[demo] all 5 nodes started ({scheme})")
        time.sleep(2.0)  # даём время на self-lookup

        # Проверим, что все логи содержат успешный bootstrap.
        for i, port in enumerate(ports):
            state_dir = STATE_ROOT / (f"seed" if i == 0 else f"{scheme}-{names[i]}")
            log_file = state_dir / "logs" / "node.log"
            if not log_file.exists():
                print(f"[demo] WARN: log missing for node {i}")
                continue
            text = log_file.read_text(encoding="utf-8")
            if i == 0:
                # seed без bootstrap: не должно быть "bootstrap result"
                if "bootstrap result" in text:
                    print(f"[demo] WARN: seed has bootstrap result?")
            else:
                if "bootstrap result: success=True" not in text:
                    print(f"[demo] ERROR: node {i} bootstrap failed")
                    return 1
                if "bootstrap self-lookup: success=" not in text:
                    print(f"[demo] WARN: node {i} self-lookup missing")

        print(f"[demo] {scheme}: bootstrap logs look good")
        return 0
    finally:
        print(f"[demo] stopping {scheme}...")
        stop_all(procs)


def main() -> int:
    STATE_ROOT.mkdir(exist_ok=True)
    LOGS_ROOT.mkdir(exist_ok=True)

    rc = run_scheme("star")
    if rc != 0:
        return rc
    rc = run_scheme("ring")
    if rc != 0:
        return rc
    print("\n=== BOOTSTRAP DEMO PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())