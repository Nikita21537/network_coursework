from __future__ import annotations

import json
from typing import Any

from .constants import (
    MSG_ERROR,
    MSG_FIND_NODE_REQUEST,
    MSG_FIND_NODE_RESPONSE,
    MSG_PING,
    MSG_PONG,
)
from .messages import (
    Contact,
    ErrorMessage,
    FindNodeRequest,
    FindNodeResponse,
    Ping,
    Pong,
)

MAX_STRING_LEN = 4096
MAX_ARRAY_LEN = 256


class PayloadError(ValueError):
    """Ошибка декодирования payload."""


def _expect_dict(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise PayloadError("payload must be a JSON object")
    return data


def _get(data: dict[str, Any], key: str, expected_type: type) -> Any:
    if key not in data:
        raise PayloadError(f"missing field: {key}")
    value = data[key]
    if not isinstance(value, expected_type):
        raise PayloadError(f"field {key} must be {expected_type.__name__}")
    return value


def _check_string(value: str, name: str) -> str:
    if len(value) > MAX_STRING_LEN:
        raise PayloadError(f"field {name} exceeds {MAX_STRING_LEN} chars")
    return value


def _decode_hex(value: str, name: str, expected_len: int | None = None) -> bytes:
    if len(value) > MAX_STRING_LEN:
        raise PayloadError(f"field {name} too long")
    try:
        raw = bytes.fromhex(value)
    except ValueError as exc:
        raise PayloadError(f"field {name} must be hex") from exc
    if expected_len is not None and len(raw) != expected_len:
        raise PayloadError(
            f"field {name} must be {expected_len} bytes, got {len(raw)}"
        )
    return raw


def _decode_contact(data: Any) -> Contact:
    d = _expect_dict(data)
    node_id = _decode_hex(
        _check_string(_get(d, "node_id", str), "node_id"), "node_id", 32
    )
    identity_algorithm = _check_string(
        _get(d, "identity_algorithm", str), "identity_algorithm"
    )
    identity_public_key = _decode_hex(
        _check_string(
            _get(d, "identity_public_key", str), "identity_public_key"
        ),
        "identity_public_key",
        32,
    )
    host = _check_string(_get(d, "host", str), "host")
    port = _get(d, "port", int)
    try:
        return Contact(
            node_id=node_id,
            identity_algorithm=identity_algorithm,
            identity_public_key=identity_public_key,
            host=host,
            port=port,
        )
    except ValueError as exc:
        raise PayloadError(str(exc)) from exc


def _encode_contact(contact: Contact) -> dict[str, Any]:
    return {
        "node_id": contact.node_id.hex(),
        "identity_algorithm": contact.identity_algorithm,
        "identity_public_key": contact.identity_public_key.hex(),
        "host": contact.host,
        "port": contact.port,
    }


def _decode_contacts(data: Any) -> tuple[Contact, ...]:
    if not isinstance(data, list):
        raise PayloadError("contacts must be a list")
    if len(data) > MAX_ARRAY_LEN:
        raise PayloadError(f"contacts exceeds {MAX_ARRAY_LEN}")
    return tuple(_decode_contact(item) for item in data)


def encode_payload(message: object) -> bytes:
    if isinstance(message, Ping):
        body = {
            "sender": _encode_contact(message.sender),
            "timestamp_ms": message.timestamp_ms,
        }
    elif isinstance(message, Pong):
        body = {
            "responder": _encode_contact(message.responder),
            "ping_timestamp_ms": message.ping_timestamp_ms,
            "responder_timestamp_ms": message.responder_timestamp_ms,
        }
    elif isinstance(message, FindNodeRequest):
        body = {
            "sender": _encode_contact(message.sender),
            "target_node_id": message.target_node_id.hex(),
        }
    elif isinstance(message, FindNodeResponse):
        body = {
            "responder": _encode_contact(message.responder),
            "target_node_id": message.target_node_id.hex(),
            "contacts": [_encode_contact(c) for c in message.contacts],
        }
    elif isinstance(message, ErrorMessage):
        body = {"code": message.code, "message": message.message}
    else:
        raise PayloadError(f"unsupported message type: {type(message).__name__}")
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")


def decode_payload(msg_type: int, payload: bytes) -> object:
    if not payload:
        raise PayloadError("empty payload")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PayloadError("invalid JSON payload") from exc
    d = _expect_dict(data)

    if msg_type == MSG_PING:
        sender = _decode_contact(_get(d, "sender", dict))
        timestamp_ms = _get(d, "timestamp_ms", int)
        return Ping(sender=sender, timestamp_ms=timestamp_ms)

    if msg_type == MSG_PONG:
        responder = _decode_contact(_get(d, "responder", dict))
        ping_ts = _get(d, "ping_timestamp_ms", int)
        resp_ts = _get(d, "responder_timestamp_ms", int)
        return Pong(
            responder=responder,
            ping_timestamp_ms=ping_ts,
            responder_timestamp_ms=resp_ts,
        )

    if msg_type == MSG_FIND_NODE_REQUEST:
        sender = _decode_contact(_get(d, "sender", dict))
        target = _decode_hex(
            _check_string(_get(d, "target_node_id", str), "target_node_id"),
            "target_node_id",
            32,
        )
        return FindNodeRequest(sender=sender, target_node_id=target)

    if msg_type == MSG_FIND_NODE_RESPONSE:
        responder = _decode_contact(_get(d, "responder", dict))
        target = _decode_hex(
            _check_string(_get(d, "target_node_id", str), "target_node_id"),
            "target_node_id",
            32,
        )
        contacts = _decode_contacts(_get(d, "contacts", list))
        return FindNodeResponse(
            responder=responder, target_node_id=target, contacts=contacts
        )

    if msg_type == MSG_ERROR:
        code = _check_string(_get(d, "code", str), "code")
        message = _check_string(_get(d, "message", str), "message")
        return ErrorMessage(code=code, message=message)

    raise PayloadError(f"unsupported message type: {msg_type}")