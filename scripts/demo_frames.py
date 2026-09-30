from __future__ import annotations

import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from p2pnode.protocol.constants import ALLOWED_TYPES, PROTOCOL_VERSION  # noqa: E402
from p2pnode.transport.framing import (  # noqa: E402
    Frame,
    FrameDecoder,
    NeedMoreData,
)


def main() -> int:
    random.seed(7)
    frames = [
        Frame(
            PROTOCOL_VERSION,
            0x01,
            0,
            os.urandom(16),
            bytes([i]) * (i % 300),
        )
        for i in range(100)
    ]
    stream = b"".join(f.encode() for f in frames)
    decoder = FrameDecoder(PROTOCOL_VERSION, 65536, set(ALLOWED_TYPES))
    decoded = []
    i = 0
    while i < len(stream):
        step = random.randint(1, 23)
        decoder.feed(stream[i : i + step])
        i += step
        while True:
            try:
                decoded.append(decoder.next_frame())
            except NeedMoreData:
                break
    assert len(decoded) == 100
    for original, got in zip(frames, decoded):
        assert original.payload == got.payload
        assert original.request_id == got.request_id
    print(f"Успешно разобрано {len(decoded)} кадров при случайном разбиении.")
    return 0


if __name__ == "__main__":
    sys.exit(main())