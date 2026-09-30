PROTOCOL_VERSION = 1

MSG_PING = 0x01
MSG_PONG = 0x02
MSG_FIND_NODE_REQUEST = 0x03
MSG_FIND_NODE_RESPONSE = 0x04
MSG_ERROR = 0x7F

ALLOWED_TYPES = frozenset(
    {
        MSG_PING,
        MSG_PONG,
        MSG_FIND_NODE_REQUEST,
        MSG_FIND_NODE_RESPONSE,
        MSG_ERROR,
    }
)

ERROR_CODES = frozenset(
    {
        "BAD_VERSION",
        "BAD_LENGTH",
        "BAD_PAYLOAD",
        "BAD_TYPE",
        "TIMEOUT",
        "INTERNAL",
        "CLOSED",
    }
)