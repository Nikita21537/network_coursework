from __future__ import annotations


import tempfile
from pathlib import Path
from typing import Iterator

from p2pnode.identity import Identity
from p2pnode.protocol.messages import Contact


def make_contact_with_key(
    host: str = "127.0.0.1",
    port: int = 9101,
) -> Contact:

    with tempfile.TemporaryDirectory() as d:
        ident = Identity.load_or_create(Path(d))
        return Contact(
            node_id=ident.node_id,
            identity_algorithm=ident.algorithm,
            identity_public_key=ident.public_key,
            host=host,
            port=port,
        )


def make_identity_contact(
    ident: Identity,
    host: str = "127.0.0.1",
    port: int = 9101,
) -> Contact:

    return Contact(
        node_id=ident.node_id,
        identity_algorithm=ident.algorithm,
        identity_public_key=ident.public_key,
        host=host,
        port=port,
    )