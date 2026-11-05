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


# Спецификация протокола — этап 2

Дополнение к `PROTOCOL.md` (этап 1). Описывает изменения и новые механизмы,
появившиеся на этапе 2: идентичность, `Contact` с публичным ключом,
k-bucket, `FIND_NODE`, итеративный lookup, bootstrap.

Версия протокола остаётся **1**: формат кадра и типы сообщений не менялись,
изменился только payload `Contact` (добавлены поля) и семантика `FIND_NODE`.

## 1. Идентичность узла

### 1.1. Алгоритм и хранение

- **Алгоритм:** Ed25519.
- **Приватный ключ:** `NODE_STATE_DIR/identity.priv` (PEM, PKCS#8, `0600` на POSIX).
- **Публичный ключ:** `NODE_STATE_DIR/identity.pub` (32 сырых байта).
- Закрытый ключ **никогда** не передаётся по сети, не пишется в лог,
  не попадает в репозиторий или образ.
- При загрузке `identity.pub` сверяется с `identity.priv`. Несовпадение —
  `ValueError`; узел не запускается.

### 1.2. Вычисление NodeID
canonical_encode(pubkey) = b"ed25519:" + pubkey # 9 + 32 = 41 байт
NodeID = SHA-256(canonical_encode(pubkey)) # 32 байта

text

Каноническая форма зафиксирована префиксом `ed25519:` — это единственный
формат на этапах 2+. Изменение формата изменит все `NodeID` и потребует
новой версии протокола.

### 1.3. Проверка контакта

При создании `Contact` (`Contact.__post_init__`) узел обязан проверить:

- `len(node_id) == 32`;
- `identity_algorithm == "ed25519"`;
- `len(identity_public_key) == 32`;
- `SHA-256(canonical_encode(identity_public_key)) == node_id`;
- `0 < port < 65536`;
- `host` не пуст.

Несовпадение ключа и `node_id` — `ValueError` при создании и
`PayloadError` при декодировании кадра. Такой контакт отклоняется,
соединение может быть закрыто с `ERROR` (`BAD_PAYLOAD`).

## 2. Contact

### 2.1. Логическая структура


Contact {
    node_id:                bytes[32],
    identity_algorithm:     "ed25519",
    identity_public_key:    bytes[32],
    host:                   str,
    port:                   uint16,
}
# 2.2. Сетевой payload

{
  "node_id": "hex(32 bytes)",
  "identity_algorithm": "ed25519",
  "identity_public_key": "hex(32 bytes)",
  "host": "127.0.0.1",
  "port": 9101
}
 # 2.3. Локальные метаданные
last_seen_ms, last_verified_ms — локальные для узла. В сеть не
передаются и не принимаются от удалённой стороны как достоверные.
Узел сам устанавливает их при получении валидного контакта.

# 2.4. Отклонение подмены
Если SHA-256(canonical_encode(pk)) != node_id:

в codec.decode_payload → PayloadError;

Dispatcher возвращает ERROR (BAD_PAYLOAD);

соединение закрывается.

Тест: T2.4 (tests/test_contact.py).

## 3. k-bucket
# 3.1. Структура
На этапе 2 используется вариант 256 фиксированных bucket
по индексу старшего установленного бита
local_node_id XOR node_id.

Bucket i покрывает диапазон [2^i, 2^(i+1) - 1],
для i = 255 — [2^255, 2^256 - 1].

Ёмкость каждого bucket — K_BUCKET_SIZE
(3 для упрощённого уровня, 4 для продвинутого).

# 3.2. LRU-порядок
Внутри bucket контакты упорядочены по времени последнего подтверждения:

[0] — самый старый (LRU);

[-1] — самый свежий.

# 3.3. Алгоритм add_or_update(contact, ping_lru)
Если contact.node_id == local_node_id → отказ (rejected_self).

Если contact.node_id уже есть в bucket:

если identity_public_key отличается → отказ (защита в глубину;
Contact обычно уже отсекает такой случай);

иначе обновить адресные данные и переместить в конец.

Если bucket не заполнен → добавить в конец.

Если bucket заполнен:

alive = ping_lru(lru);

alive == True → LRU перемещается в конец, новый контакт не добавляется
(moved_lru_to_tail = True);

alive == False → LRU удаляется, новый добавляется в конец
(evicted_dead_lru = True).

ping_lru(contact) -> bool — callback. На сервере используется
Node._ping_lru, который делает низкоуровневый PING без рекурсии
(_send_ping_only).

## 4. PING / PONG с обслуживанием bucket
# 4.1. На приёме PING
Получив валидный PING:

PingHandler вызывает routing.add_or_update(sender, ping_lru=node._ping_lru).

Отвечает PONG с тем же request_id, своим Contact и ping_timestamp_ms.

# 4.2. На приёме PONG (инициатор)
После успешного PONG (Node.ping):

routing.add_or_update(response.responder, ping_lru=node._ping_lru).

Возвращает Pong вызывающему.

# 4.3. Низкоуровневый PING для LRU-проверки
_send_ping_only(contact) -> bool:

отправляет PING;

при PONG возвращает True;

при RpcError возвращает False.

Не обновляет routing — чтобы не было рекурсии, когда add_or_update
вызывает ping_lru.

## 5. FIND_NODE
# 5.1. Запрос

{
  "sender": { ... Contact ... },
  "target_node_id": "hex(32 bytes)"
}
# 5.2. Обработка на сервере
Проверить контакт sender, вызвать routing.add_or_update(sender, ping_lru).

Вернуть до K_BUCKET_SIZE ближайших к target_node_id из routing.

Отсортировать по возрастанию XOR-расстояния.

Без дубликатов, без собственного NodeID.

# 5.3. Ответ

{
  "responder": { ... Contact ... },
  "target_node_id": "hex(32 bytes)",
  "contacts": [ { ... Contact ... } ]
}
contacts содержит ≤ K_BUCKET_SIZE записей.

Все контакты валидируются при декодировании (Contact.__post_init__).

# 5.4. Валидация на инициаторе
Node.find_node(contact, target_node_id):

проверяет isinstance(response, FindNodeResponse);

проверяет response.target_node_id == target_node_id, иначе RpcError;

добавляет response.responder в routing;

дедуплицирует по NodeID, отбрасывает self.node_id;

остальные контакты добавляет в routing через add_or_update.



## 6. Итеративный lookup
# 6.1. Параметры
ALPHA = 3 — параллелизм одной итерации.

K = K_BUCKET_SIZE — сколько ближайших возвращать.

# 6.2. Алгоритм
Старт. shortlist = до K ближайших к target из routing.
asked = пустое множество. timeouts = пустой список.

Итерация.

Отсортировать shortlist по XOR до target.

Взять до ALPHA неопрошенных ближайших.

Параллельно отправить FIND_NODE_REQUEST (ThreadPoolExecutor).

Для каждого ответа:

asked.add(node_id);

rpc_count += 1;

при ошибке — timeouts.append(node_id), пропустить;

иначе — добавить responder и все контакты из ответа в shortlist
(дубликаты по node_id игнорируются; self.node_id пропускается).

Условие остановки (зафиксировано):

все K ближайших из shortlist уже в asked; или
нет неопрошенных кандидатов в shortlist.
Финал. closest_contacts = shortlist[:K], отсортированные по XOR.
success = (target_node_id in closest_contacts).

# 6.3. LookupResult

LookupResult {
    lookup_id:          str,             # 8 hex-символов
    target_node_id:     bytes[32],
    closest_contacts:   tuple[Contact, ...],
    success:            bool,
    rpc_count:          int,
    iterations:         int,
    timeouts:           tuple[bytes, ...],  # node_id
    duration_ms:        int,
}
# 6.4. Запреты (по ТЗ, раздел 21.3)
Последовательный опрос всех узлов при ALPHA = 3.

Прямой запрос к целевому адресу, полученному от оркестратора.

Скрытая загрузка полного списка узлов.

Признание lookup успешным только потому, что все узлы заранее известны
инициатору.

Тест: T2.13 (многопереходный lookup).

## 7. Bootstrap
## 7.1. Общее
BOOTSTRAP_PEERS — список host:port через запятую.

Первый seed-узел запускается с пустым BOOTSTRAP_PEERS.

Все остальные узлы указывают хотя бы один peer.

# 7.2. Порядок присоединения (Node.join)
Для каждого host:port в BOOTSTRAP_PEERS:

ping_raw(host, port) — низкоуровневый PING без Contact получателя;

при успехе: routing.add_or_update(pong.responder), выход из цикла.

Если ни один peer не ответил → BootstrapResult(success=False, ...).
Узел продолжает работать (роль seed допустима).

Если ответил:

self-lookup: lookup_node(node, self_node_id);

BootstrapResult(success=True, bootstrap_contact, self_lookup_result, attempts).

# 7.3. BootstrapResult

BootstrapResult {
    success:             bool,
    bootstrap_contact:   Contact | None,
    self_lookup_result:  LookupResult | None,
    attempts:            int,
}
# 7.4. Схемы bootstrap
star — все новые узлы через один seed.

ring — каждый новый узел через предшественника.

На этапе 2 обе схемы работают; для продвинутого уровня добавляются tree
и multi-seed — это этап 3+.

# 7.5. Требование независимости от bootstrap (T2.14)
После успешного join узел не требует доступности bootstrap
для последующих lookup. Bootstrap-контакт становится обычным контактом
в routing и может быть вытеснен по LRU.

# 8. Новые коды ошибок
По сравнению с этапом 1 добавлены:

Код	Причина
TRUNCATED_FRAME	EOF внутри кадра (исправление этапа 1)
BAD_FLAGS	flags != 0 (исправление этапа 1)
TRUNCATED_FRAME и BAD_FLAGS фиксируются в ERROR и в логе на уровне
ERROR (protocol violation).

# 9. Валидация Contact при приёме
Проверка полей — Contact.__post_init__.

При декодировании в codec._decode_contact:

hex → bytes;

длина 32;

Contact(...) может бросить ValueError → оборачивается в PayloadError;

Dispatcher возвращает ERROR с кодом BAD_PAYLOAD.

Принимающий узел не доверяет last_seen_ms/last_verified_ms
от удалённой стороны (в сеть они не передаются).

# 10. Тайм-ауты и лимиты
Параметр	Значение
MAX_FRAME_PAYLOAD	65536
CONNECT_TIMEOUT_MS	3000
READ_TIMEOUT_MS	5000
PING_TIMEOUT_MS	5000
