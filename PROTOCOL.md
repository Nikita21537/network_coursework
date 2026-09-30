# Спецификация протокола (этап 1)

## 1. Версия протокола

`PROTOCOL_VERSION = 1`

## 2. Кадр

Big-endian, фиксированный заголовок 24 байта.

| Смещение | Поле | Размер | Тип |
|---:|---|---:|---|
| 0 | `version` | 1 | uint8 |
| 1 | `type` | 1 | uint8 |
| 2 | `flags` | 2 | uint16 |
| 4 | `request_id` | 16 | bytes |
| 20 | `payload_length` | 4 | uint32 |
| 24 | `payload` | переменный | bytes |

`flags = 0` на этапах 1–2.

## 3. Типы сообщений

| Код | Имя | Направление |
|---:|---|---|
| `0x01` | `PING` | запрос |
| `0x02` | `PONG` | ответ |
| `0x03` | `FIND_NODE_REQUEST` | запрос |
| `0x04` | `FIND_NODE_RESPONSE` | ответ |
| `0x7F` | `ERROR` | ответ/уведомление |

Коды `0x05–0x3F` зарезервированы.

## 4. Сериализация

Выбран **JSON** (UTF-8) как детерминированный, безопасный и человекочитаемый
формат. Обоснование:

- однозначное кодирование всех полей;
- проверка типов и обязательности полей на уровне кода;
- ограничение размеров строк, массивов и вложенности;
- небезопасная десериализация объектов исключена;
- единый формат для всех узлов версии 1.

Альтернативы (MessagePack, CBOR) отклонены на этапе 1 как избыточные.

## 5. Схемы payload

### 5.1. Contact

```json
{
  "node_id": "hex(32 bytes)",
  "host": "127.0.0.1",
  "port": 9101
}
```

### 5.2. PING

```json
{
  "sender": {"node_id": "...", "host": "...", "port": 9101},
  "timestamp_ms": 1700000000000
}
```

### 5.3. PONG

```json
{
  "responder": {"node_id": "...", "host": "...", "port": 9102},
  "ping_timestamp_ms": 1700000000000,
  "responder_timestamp_ms": 1700000000012
}
```

### 5.4. FIND_NODE_REQUEST

```json
{
  "sender": {"node_id": "...", "host": "...", "port": 9101},
  "target_node_id": "hex(32 bytes)"
}
```

### 5.5. FIND_NODE_RESPONSE

```json
{
  "responder": {"node_id": "...", "host": "...", "port": 9102},
  "target_node_id": "hex(32 bytes)",
  "contacts": [{"node_id": "...", "host": "...", "port": 9103}]
}
```

На этапе 1 `contacts` — пустой список (k-bucket появится на этапе 2).
Контакты сортируются по возрастанию XOR-расстояния до `target_node_id`.
Не более `K_BUCKET_SIZE` записей.

### 5.6. ERROR

```json
{
  "code": "BAD_VERSION",
  "message": "unsupported protocol version"
}
```

Коды ошибок: `BAD_VERSION`, `BAD_LENGTH`, `BAD_PAYLOAD`, `BAD_TYPE`, `INTERNAL`.

## 6. Корреляция RPC

- `request_id` генерируется `secrets.token_bytes(16)`.
- Ответ обязан содержать тот же `request_id`.
- Ответ с другим `request_id` не принимается как ответ на ожидающий запрос.

## 7. Тайм-ауты и лимиты

| Параметр | Значение |
|---|---:|
| `MAX_FRAME_PAYLOAD` | 65536 |
| `CONNECT_TIMEOUT_MS` | 3000 |
| `READ_TIMEOUT_MS` | 5000 |
| `PING_TIMEOUT_MS` | 5000 |