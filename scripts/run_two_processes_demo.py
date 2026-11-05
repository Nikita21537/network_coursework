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


def wait_for_port_free(port: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            time.sleep(0.1)
        finally:
            s.close()
    return False


def write_config(path: Path, state_dir: Path, port: int) -> None:
    path.write_text(
        "\n".join(
            [
                f"NODE_STATE_DIR={state_dir}",
                "LISTEN_HOST=127.0.0.1",
                f"LISTEN_PORT={port}",
                "BOOTSTRAP_PEERS=",
                "K_BUCKET_SIZE=3",
                "ALPHA=3",
                "CONNECT_TIMEOUT_MS=3000",
                "READ_TIMEOUT_MS=5000",
                "PING_TIMEOUT_MS=5000",
                "MAX_FRAME_PAYLOAD=65536",
                "LOG_LEVEL=INFO",
                "",
            ]
        ),
        encoding="utf-8",
    )


def start_node(name: str, state_dir: Path, port: int) -> subprocess.Popen:
    config_path = STATE_ROOT / f"{name}.env"
    write_config(config_path, state_dir, port)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    # Если пакет не установлен через pip install -e ., добавляем src в PYTHONPATH
    env["PYTHONPATH"] = str(ROOT / "src")

    kwargs = {}
    if os.name == "nt":
        # Создаём отдельную группу процессов,
        # чтобы можно было слать CTRL_BREAK_EVENT
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        [sys.executable, "-m", "p2pnode", "--config", str(config_path)],
        cwd=ROOT,
        env=env,
        **kwargs,
    )
    print(f"[{name}] started pid={proc.pid} port={port} state={state_dir}")
    return proc


def ping_pong_and_100_frames(port_a: int, port_b: int) -> None:
    import secrets
    import tempfile
    from pathlib import Path as _Path

    from p2pnode.identity import Identity
    from p2pnode.protocol.codec import encode_payload
    from p2pnode.protocol.constants import (
        ALLOWED_TYPES,
        MSG_PING,
        MSG_PONG,
        PROTOCOL_VERSION,
    )
    from p2pnode.protocol.messages import Contact, Ping
    from p2pnode.transport.framing import Frame, FrameDecoder, NeedMoreData


    with tempfile.TemporaryDirectory() as ident_tmp:
        dummy_ident = Identity.load_or_create(_Path(ident_tmp))
        sender = Contact(
            node_id=dummy_ident.node_id,
            identity_algorithm=dummy_ident.algorithm,
            identity_public_key=dummy_ident.public_key,
            host="127.0.0.1",
            port=1,
        )

    s = socket.create_connection(("127.0.0.1", port_b), timeout=3.0)
    s.settimeout(5.0)
    dec = FrameDecoder(PROTOCOL_VERSION, 65536, set(ALLOWED_TYPES))
    sent = set()
    try:
        for i in range(100):
            rid = secrets.token_bytes(16)
            sent.add(rid)
            msg = Ping(sender=sender, timestamp_ms=i)
            frame = Frame(PROTOCOL_VERSION, MSG_PING, 0, rid, encode_payload(msg))
            s.sendall(frame.encode())
        print(f"[demo] sent {len(sent)} PING frames to port {port_b}")

        received = set()
        deadline = time.monotonic() + 10.0
        while len(received) < 100 and time.monotonic() < deadline:
            chunk = s.recv(4096)
            if not chunk:
                break
            dec.feed(chunk)
            while True:
                try:
                    resp = dec.next_frame()
                except NeedMoreData:
                    break
                if resp.type == MSG_PONG:
                    received.add(resp.request_id)
                else:
                    print(f"[demo] unexpected type: {resp.type:#x}")

        assert len(received) == 100, f"received {len(received)} / 100"
        assert received == sent, "request_id mismatch between sent and received"
        print(f"[demo] received and matched {len(received)} PONG frames")
    finally:
        s.close()


def main() -> int:
    STATE_ROOT.mkdir(exist_ok=True)
    LOGS_ROOT.mkdir(exist_ok=True)

    p1, p2 = free_port(), free_port()
    d1 = STATE_ROOT / "node-01"
    d2 = STATE_ROOT / "node-02"
    d1.mkdir(parents=True, exist_ok=True)
    d2.mkdir(parents=True, exist_ok=True)

    proc1 = start_node("node-01", d1, p1)
    proc2 = start_node("node-02", d2, p2)

    try:
        if not wait_for_port(p1) or not wait_for_port(p2):
            print("ERROR: nodes did not start in time")
            return 1
        print("[demo] both nodes are listening")

        ping_pong_and_100_frames(p1, p2)

        print("[demo] sending shutdown signal to both nodes...")
        if os.name == "nt":

            proc1.send_signal(signal.CTRL_BREAK_EVENT)
            proc2.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc1.terminate()
            proc2.terminate()

        code1 = proc1.wait(timeout=10)
        code2 = proc2.wait(timeout=10)
        print(f"[demo] node-01 exited code={code1}")
        print(f"[demo] node-02 exited code={code2}")

        assert code1 == 0, f"node-01 exited with {code1}"
        assert code2 == 0, f"node-02 exited with {code2}"


        assert wait_for_port_free(p1), f"port {p1} still busy after stop"
        assert wait_for_port_free(p2), f"port {p2} still busy after stop"
        print("[demo] ports released; clean shutdown confirmed")


        for name, d in (("node-01", d1), ("node-02", d2)):
            log_file = d / "logs" / "node.log"
            text = log_file.read_text(encoding="utf-8")
            assert "node stopped" in text, f"missing 'node stopped' in {log_file}"
        print("[demo] 'node stopped' found in both logs")

        print()
        print("=== STAGE 1 DEMO PASSED ===")
        return 0
    finally:
        for name, proc in (("node-01", proc1), ("node-02", proc2)):
            if proc.poll() is None:
                print(f"[demo] force-killing {name}")
                proc.kill()
                proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())