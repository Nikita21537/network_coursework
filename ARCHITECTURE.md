# Архитектура узла (этап 1)

## 1. Подсистемы

```
┌─────────────────────────────────────────────────────────┐
│                        Node                             │
│  (запуск, конфигурация, координация подсистем)          │
└────────────┬────────────────────────────────────────────┘
             │
   ┌─────────┴──────────┬───────────────┬─────────────────┐
   │                    │               │                 │
┌──▼──────────┐  ┌──────▼──────┐  ┌─────▼──────┐  ┌───────▼──────┐
│ Transport   │  │  Protocol   │  │    RPC     │  │  Identity    │
│ TCP server  │  │  Codec      │  │ Dispatcher │  │  NodeID      │
│ connections │  │  Messages   │  │ Handlers   │  │  Keys        │
│ framing     │  │  Constants  │  │            │  │              │
└──────┬──────┘  └──────┬──────┘  └─────┬──────┘  └───────┬──────┘
       │                │               │                 │
       └────────────────┴───────────────┴─────────────────┘
                                │
                        ┌───────▼────────┐
                        │   Routing      │
                        │   Contact      │
                        │   XOR metric   │
                        └────────────────┘
```

## 2. Поток обработки входящего кадра

1. `TCPServer` принимает соединение и создаёт `Connection`.
2. `Connection` читает байты из сокета чанками.
3. `FrameDecoder` накапливает буфер и извлекает кадры:
   - если байтов меньше 24 — `NeedMoreData`;
   - если длина payload не получена — `NeedMoreData`;
   - если `payload_length > MAX_FRAME_PAYLOAD` — `ProtocolError`;
   - иначе возвращает `Frame` и продолжает разбор остатка буфера.
4. `Frame` декодируется в объект сообщения через `codec.decode_payload`.
5. `Dispatcher` выбирает обработчик по `type` и вызывает его.
6. Обработчик возвращает `Response` (для запросов) или `None`.
7. Ответ кодируется и отправляется обратно с тем же `request_id`.

## 3. Поток исходящего RPC

1. `RpcClient.send_request(contact, message, timeout)`:
   - генерирует `request_id` через `secrets.token_bytes(16)`;
   - открывает TCP-соединение (или переиспользует);
   - кодирует кадр и отправляет;
   - ожидает кадр-ответ с тем же `request_id`;
   - по тайм-ауту возвращает `RpcError`.
2. Ответ проверяется на корреляцию `request_id`; при несовпадении — отклоняется.

## 4. Разделение обязанностей

- **Transport** не знает о типах сообщений, кроме `type` как числа.
- **Protocol** не открывает сокеты и не знает о TCP.
- **RPC** не читает байты из сокета напрямую: получает готовые `Frame`.
- **Handlers** не управляют соединениями: возвращают `Response`, транспорт сам отправляет.
- **Identity** не зависит от транспорта и протокола.
- **Routing** на этапе 1 содержит только `Contact` и XOR-метрику.

## 5. Соединения

Выбран подход **новое TCP-соединение на каждый RPC** с возможностью
переиспользования через пул (задел на этап 2). Это упрощает корреляцию
`request_id` и соответствует требованию «не предполагать, что один `read()`
возвращает ровно один кадр».

Пулы соединений и их жизненный цикл описаны в `PROTOCOL.md`.

## 6. Тайм-ауты

| Параметр | Значение | Где применяется |
|---|---:|---|
| `CONNECT_TIMEOUT_MS` | 3000 | `socket.create_connection` |
| `READ_TIMEOUT_MS` | 5000 | чтение кадра |
| `PING_TIMEOUT_MS` | 5000 | ожидание `PONG` |

## 7. Обработка ошибок

- Ошибка декодирования → отправка `ERROR` (если возможно) и закрытие соединения.
- Превышение `MAX_FRAME_PAYLOAD` → отклонение **до** выделения буфера.
- Несовпадение `request_id` в ответе → ответ относится к неизвестному RPC, игнорируется.
- Разрыв внутри кадра → соединение закрывается, ресурсы освобождаются.
- Ошибка одного соединения **не завершает процесс узла**.

## Архитектура узла — этап 2

Дополнение к `ARCHITECTURE.md` (этап 1). Описывает, как на этапе 2
изменились и добавились подсистемы: идентичность (Ed25519), расширенный
`Contact`, k-bucket и `RoutingTable`, обработка `PING`/`FIND_NODE`,
итеративный lookup, bootstrap.

## 1. Подсистемы
```
┌───────────────────────────────────────────────────────────┐
│ Node │
│ запуск, конфигурация, bootstrap, координация подсистем │
└───────────────┬───────────────────────────────────────────┘
│
┌─────────────┴───────────┬────────────┬────────────────┐
│ │ │ │
┌─▼──────────┐ ┌──────────▼───┐ ┌─────▼─────┐ ┌───────▼──────┐
│ Transport │ │ Protocol │ │ RPC │ │ Identity │
│ TCP, кадры │ │ JSON-кодек │ │ Dispatcher│ │ Ed25519, ID │
└─────┬──────┘ └──────┬───────┘ └─────┬─────┘ └───────┬──────┘
│ │ │ │
└────────────────┴────────────────┴────────────────┘
│
┌──────────▼──────────┐
│ Routing │
│ XOR, k-bucket, │
│ RoutingTable, │
│ lookup, bootstrap │
└─────────────────────┘

```

По сравнению с этапом 1 добавлены:

```
| Модуль | Что делает |
|---|---|
| `identity/node_id.py` | Ed25519, `NodeID`, `sign`/`verify`, загрузка/сохранение ключей |
| `protocol/messages.py` | `Contact` с `identity_algorithm` и `identity_public_key` |
| `protocol/codec.py` | Сериализация ключа, `PayloadError` на подмене |
| `routing/kbucket.py` | Один k-bucket с LRU |
| `routing/table.py` | 256 bucket'ов, `find_closest`, `snapshot` |
| `routing/lookup.py` | Итеративный lookup |
| `node/bootstrap.py` | `join_network`, `BootstrapResult`, `parse_peer` |
```

## 2. Идентичность

### 2.1. Хранение

- Приватный ключ — `NODE_STATE_DIR/identity.priv` (PEM PKCS#8, `0600`).
- Публичный ключ — `NODE_STATE_DIR/identity.pub` (32 сырых байта).
- При загрузке `identity.pub` сверяется с `identity.priv`; рассинхронизация →
  `ValueError`, узел не стартует.

### 2.2. Класс `Identity`

```
@dataclass(frozen=True)
class Identity:
    node_id:      bytes
    public_key:   bytes
    _private_key: Ed25519PrivateKey

    @property algorithm -> "ed25519"
    def sign(data) -> bytes
    def verify(sig, data) -> bool
```
    @staticmethod load_or_create(state_dir) -> Identity
_private_key — только в памяти, repr не выводит содержимое.

sign/verify — задел на этап 3 (подписанные NodeRecord).

# 2.3. NodeID

canonical_encode(pk) = b"ed25519:" + pk
NodeID               = SHA-256(canonical_encode(pk))
Формат зафиксирован префиксом ed25519: — единственный на этапах 2+.

# 2.4. Проверка контакта
Contact.__post_init__ выполняет:

len(node_id) == 32;

identity_algorithm == "ed25519";

len(identity_public_key) == 32;

0 < port < 65536;

host != "";

SHA-256(canonical_encode(pk)) == node_id.

Несовпадение ключа и NodeID — ValueError при создании,
PayloadError при декодировании.

## 3. Contact
# 3.1. Логическая структура
```
Contact {
    node_id:             bytes[32],
    identity_algorithm:  "ed25519",
    identity_public_key: bytes[32],
    host:                str,
    port:                uint16,
}
```
# 3.2. Локальные метаданные
last_seen_ms, last_verified_ms — локальные для узла; в сеть
не передаются и не принимаются от удалённой стороны.

# 3.3. Валидация в codec._decode_contact
Прочитать node_id, identity_algorithm, identity_public_key,
host, port из JSON.

Проверить hex-декодирование и длины.

Создать Contact(...); ValueError → PayloadError.

Dispatcher → ERROR (BAD_PAYLOAD).

## 4. k-bucket
# 4.1. Структура KBucket
```
class KBucket:
    capacity:    int             # K_BUCKET_SIZE
    range_low:   int             # 2^i
    range_high:  int             # 2^(i+1) - 1, для i=255: 2^256 - 1
    index:       int             # 0..255
    _contacts:   list[Contact]   # LRU, [0] самый старый

    def add_or_update(contact, ping_lru) -> AddResult
    def touch(node_id) -> bool
    def remove(node_id) -> bool
    def find_closest(target_node_id, limit) -> list[Contact]
AddResult:
```
```
AddResult {
    added:                bool,
    updated:              bool,
    moved_lru_to_tail:    bool,
    evicted_dead_lru:     bool,
    rejected_full_alive:  bool,
}
```
# 4.2. Алгоритм add_or_update
Существующий node_id:

тот же identity_public_key → updated=True, переместить в конец;

другой identity_public_key → отказ (защита в глубину; обычно
Contact.__post_init__ уже отсекает такой случай).

Bucket не заполнен → added=True, добавить в конец.

Bucket заполнен:

ping_lru(lru) возвращает True → moved_lru_to_tail=True,
LRU в конец, новый отброшен;

False → evicted_dead_lru=True, LRU удалить, новый в конец.

ping_lru(contact) -> bool — callback; на сервере это
Node._ping_lru (низкоуровневый PING без рекурсии, см. §5.4).

##  5. RoutingTable и Routing
#5.1. Структура RoutingTable
```
class RoutingTable:
    local_node_id:  bytes
    k_bucket_size:  int
    _buckets:       list[KBucket]  # 256 фиксированных

    def bucket_index_for(node_id) -> int       # -1 для собственного
    def add_or_update(contact, ping_lru) -> RoutingAddResult
    def remove(node_id) -> bool
    def get(node_id) -> Contact | None
    def find_closest(target_node_id, limit) -> list[Contact]
    def all_contacts() -> list[Contact]
    def snapshot() -> list[dict]
RoutingAddResult расширяет AddResult:
```
```
RoutingAddResult {
    added, updated, moved_lru_to_tail, evicted_dead_lru,
    rejected_full_alive, rejected_self,
    bucket_index: int,
}
```
# 5.2. Индекс bucket'а
```
if node_id == local_node_id: return -1
distance = XOR(local_node_id, node_id)
index = distance.bit_length() - 1     # 0..255
Собственный NodeID в таблицу не добавляется.
```
# 5.3. find_closest
Собирает все контакты из всех bucket'ов.

Сортирует по XOR до target_node_id (как беззнаковым 256-битным).

Возвращает ≤ limit.

# 5.4. Обратная связь с Node
RoutingTable не знает о сети. ping_lru передаётся из Node:


node.routing.add_or_update(contact, ping_lru=node._ping_lru)
Node._ping_lru → _send_ping_only → низкоуровневый PING.
Это разрывает потенциальную рекурсию:

add_or_update → ping_lru(lru) → _send_ping_only(lru)  # БЕЗ add_or_update
## 6. Обработчики и Node
# 6.1. PingHandler
routing.add_or_update(sender, ping_lru=node._ping_lru).

Вернуть Pong(responder=local_contact(), ...).

# 6.2. FindNodeHandler
routing.add_or_update(sender, ping_lru=node._ping_lru).

contacts = routing.find_closest(target, limit=K).

Вернуть FindNodeResponse(responder=local_contact(), target, contacts).

# 6.3. Node.ping (инициатор)
Отправить PING.

Валидировать Pong.

routing.add_or_update(responder, ping_lru=node._ping_lru).

# 6.4. Node.find_node (инициатор)
Отправить FIND_NODE_REQUEST.

Валидировать:

тип FindNodeResponse;

target_node_id совпадает.

Дедуплицировать по node_id, отбросить self.node_id.

routing.add_or_update(responder, ...).

routing.add_or_update для каждого нового контакта.

Вернуть FindNodeResponse.

# 6.5. Node.ping_raw(host, port)
Низкоуровневый PING по адресу для bootstrap:

Сформировать Ping(sender=local_contact()).

Открыть TCP по (host, port).

Отправить кадр, дождаться PONG.

Валидировать request_id, вернуть Pong.

Использует local_contact() в sender, но получает responder от peer —
так узел узнаёт полноценный Contact по известному адресу.

## 7. Итеративный lookup
# 7.1. Модуль routing/lookup.py

def lookup_node(node, target_node_id, alpha=3) -> LookupResult
LookupResult (frozen dataclass):

```
LookupResult {
    lookup_id:         str,                # 8 hex
    target_node_id:    bytes,
    closest_contacts:  tuple[Contact, ...],
    success:           bool,               # target ∈ closest_contacts
    rpc_count:         int,
    iterations:        int,
    timeouts:          tuple[bytes, ...],
    duration_ms:       int,
}
```
# 7.2. Поток
shortlist ← routing.find_closest(target, k).

asked ← ∅.

Итерация:

sorted_candidates = sorted(shortlist, key=xor_to_target).
Если все k ближайших уже в asked → stop.
to_ask = [c for c in sorted_candidates if c.node_id not in asked][:alpha].
Если to_ask == [] → stop.
ThreadPoolExecutor(max_workers=len(to_ask)) → node.find_node(c, target).
По результату:
ошибка → timeouts, asked.add;
успех → shortlist[responder] = …, все contacts в shortlist.
final = sorted(shortlist)[:k].

success = target in final.

# 7.3. Изоляция ошибок
RpcError — фиксируется как тайм-аут.

Прочие исключения — log.exception, продолжение.

Один недоступный контакт не ломает lookup.

# 7.4. Условие остановки
Зафиксировано в PROTOCOL_STAGE2.md и PROTOCOL.md (§13):

Все K ближайших к target уже опрошены; или

Некого больше спросить.

## 8. Bootstrap
# 8.1. node/bootstrap.py
```
@dataclass(frozen=True)
class BootstrapResult:
    success:             bool
    bootstrap_contact:   Contact | None
    self_lookup_result:  LookupResult | None
    attempts:            int

def parse_peer(peer: str) -> tuple[str, int]
def join_network(node, peers, self_lookup=True) -> BootstrapResult
```
# 8.2. Node.join
Обёртка над join_network:

вызывается из __main__.py после node.start();

при ошибке логируется bootstrap failed; continuing as standalone;

узел не падает — работает как seed.

# 8.3. Сценарий
```
__main__.py:
    node = Node(cfg)
    node.start()
    if cfg.bootstrap_peers:
        try:
            result = node.join(cfg.bootstrap_peers)
            log.info("bootstrap result: success=%s ...", ...)
        except Exception:
            log.exception("bootstrap failed")
```
# 9. Изменения в TCPServer/Connection (этап 1, но актуально)
Активные соединения хранятся в dict[int, Connection] — Connection
не хэшируется.

TCPServer.stop():

закрывает слушающий сокет;
закрывает все активные Connection;
join accept-поток и worker-потоки;
очищает реестры.
Connection.recv_frames при EOF:

has_buffered_data() == False → чистое закрытие;

True → ProtocolError("TRUNCATED_FRAME").

FrameDecoder:

flags != 0 → ProtocolError("BAD_FLAGS");

payload_length > MAX — отклонение до выделения буфера.

# 10. Обработка сигналов
__main__.py:

SIGINT — все платформы;

SIGTERM — Linux/macOS;

SIGBREAK — Windows (при CTRL_BREAK_EVENT).

В обоих случаях вызывается node.stop(), в логе — node stopped.
