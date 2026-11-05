from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from p2pnode.identity import Identity, compute_node_id
from p2pnode.protocol.codec import PayloadError, decode_payload, encode_payload
from p2pnode.protocol.constants import MSG_PING
from p2pnode.protocol.messages import Contact, Ping


def _make_identity() -> Identity:
    with tempfile.TemporaryDirectory() as d:
        ident = Identity.load_or_create(Path(d))
        # Копируем поля, чтобы TemporaryDirectory не удалил ключ
        return Identity(
            node_id=ident.node_id,
            public_key=ident.public_key,
            _private_key=ident._private_key,
        )


def _valid_contact() -> Contact:
    ident = _make_identity()
    return Contact(
        node_id=ident.node_id,
        identity_algorithm=ident.algorithm,
        identity_public_key=ident.public_key,
        host="127.0.0.1",
        port=9101,
    )


class ContactValidationTests(unittest.TestCase):

    def test_valid_contact_accepted(self) -> None:
        c = _valid_contact()
        self.assertEqual(len(c.node_id), 32)
        self.assertEqual(len(c.identity_public_key), 32)
        self.assertEqual(c.identity_algorithm, "ed25519")

    def test_t24_substituted_node_id_rejected(self) -> None:
        ident = _make_identity()
        wrong_node_id = bytes(b ^ 0xFF for b in ident.node_id)  # инверсия битов
        with self.assertRaises(ValueError) as ctx:
            Contact(
                node_id=wrong_node_id,
                identity_algorithm=ident.algorithm,
                identity_public_key=ident.public_key,
                host="127.0.0.1",
                port=9101,
            )
        self.assertIn("node_id does not match", str(ctx.exception))

    def test_t24_substituted_public_key_rejected(self) -> None:
        ident = _make_identity()
        other = _make_identity()
        with self.assertRaises(ValueError) as ctx:
            Contact(
                node_id=ident.node_id,
                identity_algorithm=ident.algorithm,
                identity_public_key=other.public_key,
                host="127.0.0.1",
                port=9101,
            )
        self.assertIn("node_id does not match", str(ctx.exception))

    def test_wrong_algorithm_rejected(self) -> None:
        ident = _make_identity()
        with self.assertRaises(ValueError):
            Contact(
                node_id=ident.node_id,
                identity_algorithm="rsa",  # не ed25519
                identity_public_key=ident.public_key,
                host="127.0.0.1",
                port=9101,
            )

    def test_wrong_pubkey_length_rejected(self) -> None:
        ident = _make_identity()
        with self.assertRaises(ValueError):
            Contact(
                node_id=ident.node_id,
                identity_algorithm=ident.algorithm,
                identity_public_key=b"\x00" * 31,  # 31, не 32
                host="127.0.0.1",
                port=9101,
            )

    def test_wrong_node_id_length_rejected(self) -> None:
        ident = _make_identity()
        with self.assertRaises(ValueError):
            Contact(
                node_id=b"\x00" * 31,  # 31, не 32
                identity_algorithm=ident.algorithm,
                identity_public_key=ident.public_key,
                host="127.0.0.1",
                port=9101,
            )

    def test_empty_host_rejected(self) -> None:
        ident = _make_identity()
        with self.assertRaises(ValueError):
            Contact(
                node_id=ident.node_id,
                identity_algorithm=ident.algorithm,
                identity_public_key=ident.public_key,
                host="",
                port=9101,
            )

    def test_port_out_of_range_rejected(self) -> None:
        ident = _make_identity()
        for bad_port in (0, 65536, -1):
            with self.assertRaises(ValueError):
                Contact(
                    node_id=ident.node_id,
                    identity_algorithm=ident.algorithm,
                    identity_public_key=ident.public_key,
                    host="127.0.0.1",
                    port=bad_port,
                )

    def test_t24_codec_rejects_mismatched_contact(self) -> None:
        ident = _make_identity()
        wrong_node_id = bytes(b ^ 0xFF for b in ident.node_id)
        # Собираем JSON с подменой: node_id ≠ compute_node_id(pubkey)
        import json
        body = {
            "sender": {
                "node_id": wrong_node_id.hex(),
                "identity_algorithm": ident.algorithm,
                "identity_public_key": ident.public_key.hex(),
                "host": "127.0.0.1",
                "port": 9101,
            },
            "timestamp_ms": 123,
        }
        raw = json.dumps(body).encode("utf-8")
        with self.assertRaises(PayloadError) as ctx:
            decode_payload(MSG_PING, raw)
        self.assertIn("node_id does not match", str(ctx.exception))

    def test_roundtrip_with_real_identity(self) -> None:

        c = _valid_contact()
        msg = Ping(sender=c, timestamp_ms=42)
        decoded = decode_payload(MSG_PING, encode_payload(msg))
        self.assertEqual(decoded.sender.node_id, c.node_id)
        self.assertEqual(decoded.sender.identity_public_key, c.identity_public_key)


if __name__ == "__main__":
    unittest.main()