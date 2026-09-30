from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from p2pnode.protocol.constants import ALLOWED_TYPES, PROTOCOL_VERSION  # noqa: E402
from p2pnode.transport.framing import FrameDecoder, ProtocolError  # noqa: E402


def check(name: str, header: bytes) -> None:
    decoder = FrameDecoder(PROTOCOL_VERSION, 65536, set(ALLOWED_TYPES))
    decoder.feed(header)
    try:
        decoder.next_frame()
    except ProtocolError as exc:
        print(f"[OK] {name}: code={exc.code} message={exc.message}")
        return
    print(f"[FAIL] {name}: нарушение не обнаружено")
    raise SystemExit(1)


def main() -> int:
    print("Негативные тесты кадрирования этапа 1")
    check(
        "неизвестная версия",
        struct.pack(">BBH16sI", 99, 0x01, 0, os.urandom(16), 0),
    )
    check(
        "неизвестный тип",
        struct.pack(">BBH16sI", PROTOCOL_VERSION, 0x55, 0, os.urandom(16), 0),
    )
    check(
        "завышенная длина",
        struct.pack(">BBH16sI", PROTOCOL_VERSION, 0x01, 0, os.urandom(16), 65537),
    )
    print("Все негативные тесты пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())