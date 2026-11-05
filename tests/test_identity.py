from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path


from p2pnode.identity import (
    IDENTITY_ALGORITHM,
    Identity,
    canonical_encode_public_key,
    compute_node_id,
)


class IdentityTests(unittest.TestCase):

    def test_t21_node_id_stable_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)
            id1 = Identity.load_or_create(state)
            id2 = Identity.load_or_create(state)
            self.assertEqual(id1.node_id, id2.node_id)
            self.assertEqual(id1.public_key, id2.public_key)
            self.assertEqual(id1.node_id_hex, id2.node_id_hex)

    def test_t22_two_nodes_have_different_node_ids(self) -> None:
        with (
            tempfile.TemporaryDirectory() as d1,
            tempfile.TemporaryDirectory() as d2,
        ):
            id1 = Identity.load_or_create(Path(d1))
            id2 = Identity.load_or_create(Path(d2))
            self.assertNotEqual(id1.node_id, id2.node_id)
            self.assertNotEqual(id1.public_key, id2.public_key)

    def test_t23_node_id_matches_public_key(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ident = Identity.load_or_create(Path(d))
            # Пересчитываем NodeID из public_key
            recomputed = compute_node_id(ident.public_key)
            self.assertEqual(ident.node_id, recomputed)

            # И независимо проверяем через hashlib
            canonical = canonical_encode_public_key(ident.public_key)
            expected = hashlib.sha256(canonical).digest()
            self.assertEqual(ident.node_id, expected)

    def test_identity_algorithm_is_ed25519(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ident = Identity.load_or_create(Path(d))
            self.assertEqual(ident.algorithm, IDENTITY_ALGORITHM)
            self.assertEqual(IDENTITY_ALGORITHM, "ed25519")

    def test_sign_verify_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ident = Identity.load_or_create(Path(d))
            msg = b"hello world"
            sig = ident.sign(msg)
            self.assertTrue(ident.verify(sig, msg))
            self.assertFalse(ident.verify(sig, b"hello worlD"))

    def test_partial_state_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)
            Identity.load_or_create(state)
            # Удаляем pub
            (state / "identity.pub").unlink()
            with self.assertRaises(RuntimeError):
                Identity.load_or_create(state)

    def test_mismatched_keys_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            id1 = Identity.load_or_create(Path(d1))
            id2 = Identity.load_or_create(Path(d2))
            # Копируем приватный ключ от id1, но публичный от id2 — рассинхрон
            priv = (Path(d1) / "identity.priv").read_bytes()
            (Path(d2) / "identity.priv").write_bytes(priv)
            with self.assertRaises(ValueError):
                Identity.load_or_create(Path(d2))


if __name__ == "__main__":
    unittest.main()