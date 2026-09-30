from __future__ import annotations

import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from p2pnode.config import Config  # noqa: E402
from p2pnode.logging_setup import setup_logging  # noqa: E402
from p2pnode.node.node import Node  # noqa: E402
from p2pnode.protocol.codec import encode_payload  # noqa: E402
from p2pnode.protocol.constants import (  # noqa: E402
    ALLOWED_TYPES,
    PROTOCOL_VERSION,
)
from p2pnode.protocol.messages import Contact, Ping  # noqa: E402
from p2pnode.transport.framing import (  # noqa: E402
    Frame,
    FrameDecoder,
    NeedMoreData,
    ProtocolError,
)


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def make_config(port: int, state_dir: Path) -> Config:
    return Config(
        node_state_dir=state_dir,
        listen_host="127.0.0.1",
        listen_port=port,
        bootstrap_peers=(),
        node_id_bits=256,
        k_bucket_size=3,
        alpha=3,
        connect_timeout_ms=3000,
        read_timeout_ms=5000,
        ping_timeout_ms=5000,
        max_frame_payload=65536,
        protocol_version=PROTOCOL_VERSION,
        log_level="INFO",
    )


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def main() -> int:
    logs_dir = ROOT / "logs"
    state_root = ROOT / "state"
    state_root.mkdir(exist_ok=True)
    setup_logging("INFO", logs_dir)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        p1, p2 = free_port(), free_port()
        n1 = Node(make_config(p1, tmp_path / "node-01"))
        n2 = Node(make_config(p2, tmp_path / "node-02"))

        section("1. Запуск TCP-серверов")
        n1.start()
        n2.start()
        time.sleep(0.3)
        print(f"node-01: 127.0.0.1:{p1} id={n1.identity.short_id}")
        print(f"node-02: 127.0.0.1:{p2} id={n2.identity.short_id}")

        try:
            contact2 = Contact(
                node_id=n2.identity.node_id, host="127.0.0.1", port=p2
            )
            contact1 = Contact(
                node_id=n1.identity.node_id, host="127.0.0.1", port=p1
            )

            section("2. Обмен PING/PONG")
            pong = n1.ping(contact2)
            print(f"node-01 -> node-02: PING; ответ: {type(pong).__name__}")
            pong2 = n2.ping(contact1)
            print(f"node-02 -> node-01: PING; ответ: {type(pong2).__name__}")
            assert pong.responder.node_id == n2.identity.node_id
            assert pong2.responder.node_id == n1.identity.node_id

            section("3. Передача 100 кадров переменной длины")
            s = socket.create_connection(("127.0.0.1", p2), timeout=2.0)
            s.settimeout(2.0)
            try:
                sent = 0
                for i in range(100):
                    payload = bytes([i % 251]) * (i % 200)
                    frame = Frame(
                        PROTOCOL_VERSION, 0x01, 0, i.to_bytes(16, "big"), payload
                    )
                    s.sendall(frame.encode())
                    sent += 1
                print(f"отправлено {sent} кадров")
            finally:
                s.close()

            section("4. Склеенные и разделённые кадры")
            decoder = FrameDecoder(
                PROTOCOL_VERSION, 65536, set(ALLOWED_TYPES)
            )
            f1 = Frame(PROTOCOL_VERSION, 0x01, 0, b"\x00" * 16, b"aaa")
            f2 = Frame(PROTOCOL_VERSION, 0x01, 0, b"\x01" * 16, b"bbb")
            decoder.feed(f1.encode() + f2.encode())
            got1 = decoder.next_frame()
            got2 = decoder.next_frame()
            assert got1.payload == b"aaa" and got2.payload == b"bbb"
            print("склеенные кадры разобраны в правильном порядке")

            decoder = FrameDecoder(
                PROTOCOL_VERSION, 65536, set(ALLOWED_TYPES)
            )
            data = f1.encode()
            decoder.feed(data[:10])
            try:
                decoder.next_frame()
            except NeedMoreData:
                pass
            decoder.feed(data[10:])
            got = decoder.next_frame()
            assert got.payload == b"aaa"
            print("разделённый кадр собран корректно")

            section("5. Отклонение завышенной длины payload")
            import struct

            bad_header = struct.pack(
                ">BBH16sI", PROTOCOL_VERSION, 0x01, 0, b"\x00" * 16, 65537
            )
            decoder = FrameDecoder(
                PROTOCOL_VERSION, 65536, set(ALLOWED_TYPES)
            )
            decoder.feed(bad_header)
            try:
                decoder.next_frame()
                print("ОШИБКА: завышенная длина принята")
                return 1
            except ProtocolError as exc:
                print(f"ожидаемое отклонение: code={exc.code} message={exc.message}")

            section("РЕЗУЛЬТАТ")
            print("Все проверки этапа 1 пройдены успешно.")
            print(f"Журналы: {logs_dir}")
            return 0
        finally:
            n1.stop()
            n2.stop()


if __name__ == "__main__":
    sys.exit(main())