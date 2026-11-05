# Защищённая оверлейная P2P-сеть — Этап 1

Реализация **этапа 1** курсовой работы: транспорт TCP, собственное кадрирование,
сериализация payload, диспетчеризация сообщений и обработка ошибок протокола.

Этапы 1–2 не включают STORE/FIND_VALUE, TLS/AKE, туннели и передачу файлов.
Интерфейсы спроектированы так, чтобы эти функции добавлялись без изменения
базовой архитектуры.

## Требования

- Python 3.11 или новее
- Linux / macOS / Windows (проверено на Linux)
- Внешние зависимости отсутствуют

## Быстрый старт

```
git clone <url-репозитория>
cd p2p-overlay-node

# Запуск двух узлов и автоматического PING/PONG-сценария
python -m scripts.run_two_nodes_demo
```

Скрипт:
1. поднимает два узла на `127.0.0.1:9101` и `127.0.0.1:9102`;
2. устанавливает TCP-соединение;
3. выполняет обмен `PING`/`PONG`;
4. передаёт 100 кадров переменной длины;
5. проверяет обработку склеенных и разделённых кадров;
6. проверяет отклонение завышенной длины payload;
7. сохраняет журналы в `./logs/`.

## Запуск одного узла

```
python -m p2pnode --config configs/node-01.env
```

или через переменные окружения:

```
NODE_STATE_DIR=./state/node-01 \
LISTEN_HOST=0.0.0.0 LISTEN_PORT=9101 \
BOOTSTRAP_PEERS=node-02:9102 \
python -m p2pnode
```

## Тесты

```
python -m unittest discover -s tests -v
```

## Демонстрации

| Скрипт | Назначение |
|---|---|
| `scripts/run_two_nodes_demo.py` | Полный приёмочный сценарий этапа 1 |
| `scripts/demo_frames.py` | Демонстрация кадрирования и частичных чтений |
| `scripts/demo_negative.py` | Негативные тесты (версия, тип, длина) |

## Структура проекта

```
src/p2pnode/
├── transport/   TCP-соединения, чтение/запись, кадрирование, тайм-ауты
├── protocol/    константы версии, типы сообщений, кодеки
├── identity/    ключи, NodeID, загрузка/сохранение состояния
├── routing/     Contact, XOR-метрика (k-bucket появится на этапе 2)
├── rpc/         обработчики PING/PONG, FIND_NODE (заглушка)
└── node/        запуск узла, конфигурация, координация подсистем
```

## Формат кадра

Все многобайтные целые — big-endian. Заголовок фиксирован: **24 байта**.

| Смещение | Поле | Размер |
|---:|---|---:|
| 0 | `version` | 1 |
| 1 | `type` | 1 |
| 2 | `flags` | 2 |
| 4 | `request_id` | 16 |
| 20 | `payload_length` | 4 |
| 24 | `payload` | переменный |

Подробности — в `PROTOCOL.md`.

## Ограничения этапа 1

- DHT-overlay ещё не строится: k-bucket появится на этапе 2;
- `FIND_NODE_REQUEST` / `FIND_NODE_RESPONSE` закодированы и диспетчеризуются,
  но возвращают пустой список контактов (заглушка);
- защита канала (TLS/AKE) появится на этапе 3.

## Лицензия

MIT. См. `LICENSE`.

# Этап 2: идентичность, Kademlia DHT, bootstrap

Реализация **второго этапа** курсовой работы: Ed25519-идентичность,
ограниченная таблица маршрутизации Kademlia, операции `PING`/`FIND_NODE`,
итеративный lookup с `ALPHA = 3`, bootstrap через известный адрес.

## Требования

- Python 3.11+.
- **Внешняя зависимость: `cryptography >= 42`** (Ed25519).
- Linux / macOS / Windows.

## Установка


# pip install -e .
## Что добавляет этап 2
Ed25519-идентичность.
При первом запуске — генерация Ed25519-пары.

Приватный ключ: NODE_STATE_DIR/identity.priv (PEM PKCS#8, 0600).

Публичный: NODE_STATE_DIR/identity.pub (32 сырых байта).

NodeID = SHA-256(b"ed25519:" + pubkey) — устойчив при перезапуске.

Contact с публичным ключом.
Проверка compute_node_id(pubkey) == node_id — подмена ключа или NodeID
отклоняется (ValueError при создании, PayloadError при декодировании).

# k-bucket с LRU.
При полном bucket — PING к LRU:

LRU жив → перемещается в конец, новый контакт не добавляется;

LRU мёртв → удаляется, новый добавляется в конец.

# RoutingTable.
256 фиксированных bucket по индексу старшего установленного бита
local_node_id XOR node_id.

# PING/PONG обслуживают bucket.
При получении PING и при успешном PONG контакт добавляется/обновляется
в routing с callback ping_lru.

# FIND_NODE.
Возвращает до K_BUCKET_SIZE ближайших к target_node_id из routing,
отсортированных по XOR, без дубликатов, без собственного NodeID.

Итеративный lookup.
ALPHA = 3, параллельные запросы через ThreadPoolExecutor,
корректное условие остановки:

все K ближайших опрошены или

некого больше спросить.

# Bootstrap.
Node.join(bootstrap_peers):

ping_raw(host, port) до первого успеха;

добавление bootstrap-контакта в routing;

self-lookup (lookup_node(self_node_id)).

Конфигурация
Параметры, которые появились/уточнились на этапе 2:
```
Параметр	Значение	Назначение
K_BUCKET_SIZE	3 (basic) / 4 (advanced)	Ёмкость каждого bucket
ALPHA	3	Параллелизм lookup
BOOTSTRAP_PEERS	host:port,host:port,...	Адреса для join
```

# Запуск узла с bootstrap

python -m p2pnode --config configs/node-02.env
где в configs/node-02.env:
```
env
NODE_STATE_DIR=./state/node-02
LISTEN_HOST=127.0.0.1
LISTEN_PORT=9102
BOOTSTRAP_PEERS=127.0.0.1:9101
K_BUCKET_SIZE=3
ALPHA=3
```
В логе после старта:

```
bootstrap: PING 127.0.0.1:9101
bootstrap: joined via 127.0.0.1:9101 node=xxxxxxxx
bootstrap result: success=True attempts=1 bootstrap_node=xxxxxxxx routing_size=1
bootstrap self-lookup: success=True contacts=N rpc=M iters=K duration_ms=X
Если bootstrap-узел недоступен — узел продолжает работать как seed
(ошибка логируется, но процесс не падает).
```
# Демонстрации

scripts/run_bootstrap_demo.py — 5 subprocess-узлов
Проверяет, что bootstrap идёт через реальный TCP:

star — все новые узлы через один seed;

ring — каждый новый через предшественника.

```
rm -rf state/seed state/star-n* state/ring-n*
python scripts/run_bootstrap_demo.py
Ожидаемо: в логах не-seed узлов bootstrap result: success=True.

scripts/run_stage2_demo.py — 12 in-process узлов, 10+ lookup
```
Полный сценарий раздела 25 ТЗ:


12 узлов in-process (пилотный масштаб N = 12).

Bootstrap star и ring.

У каждого не-seed — PING bootstrap и self-lookup.

Выгрузка routing_<scheme>_n<i>.json — таблица маршрутизации каждого узла.

10 контрольных lookup, где цель отсутствует в routing инициатора.

Отключение seed; повторный lookup между уже присоединившимися.

Проверка невырожденности: ≥80% узлов знают < N-1 контактов.


rm -rf state/stage2
python scripts/run_stage2_demo.py
Ожидаемо: === STAGE 2 DEMO PASSED ===.

Артефакты в state/stage2/:

```
state/stage2/
├── summary.json
├── star/
│   ├── routing_star-n0.json ... routing_star-n11.json
│   └── lookups_star.csv
└── ring/
    ├── routing_ring-n0.json ... routing_ring-n11.json
    └── lookups_ring.csv
routing_<scheme>_n<i>.json — snapshot таблицы маршрутизации узла
(bucket'ы с контактами).
```
lookups_<scheme>.csv — 10 контрольных lookup: инициатор, цель,
число RPC, число итераций, длительность, флаг target_found.

summary.json — сводка по обеим схемам.

##  Тесты этапа 2

python -m unittest discover -s tests -v
Покрытие этапа 2 — 48 тестов из общих 80:

Структура модулей этапа 2
```
src/p2pnode/
├── identity/
│   ├── __init__.py
│   └── node_id.py          # Ed25519, Identity, compute_node_id
├── routing/
│   ├── __init__.py
│   ├── contact.py          # xor_distance, sort_by_distance
│   ├── kbucket.py          # KBucket, AddResult
│   ├── table.py            # RoutingTable, RoutingAddResult
│   └── lookup.py           # LookupResult, lookup_node
├── node/
│   ├── __init__.py
│   ├── node.py             # ping_raw, find_node, join
│   └── bootstrap.py        # BootstrapResult, parse_peer, join_network
├── protocol/
│   ├── messages.py         # Contact с identity_public_key
│   └── codec.py            # сериализация ключа и проверка node_id
└── rpc/
    └── handlers.py         # PingHandler, FindNodeHandler
```
3# Ключевые технические решения
Идентичность
Приватный ключ хранится только в NODE_STATE_DIR/identity.priv.

При загрузке identity.pub сверяется с identity.priv — рассинхронизация
вызывает ValueError.

При получении Contact из сети проверяется SHA-256(canonical_encode(pk)) == node_id.

Каноническая форма — b"ed25519:" + pk, зафиксирована константой.

RoutingTable и k-bucket
256 bucket'ов фиксированного размера — проще и детерминированнее
динамического разбиения.

Внутри bucket — LRU ([0] самый старый).

Живой LRU не вытесняется без PING.

Собственный NodeID не хранится в таблице.

# Итеративный lookup
ALPHA = 3 — требование ТЗ.

ThreadPoolExecutor — параллельные запросы.

# Условие остановки:

все K ближайших опрошены; или
некого больше спросить.
Тайм-ауты фиксируются в LookupResult.timeouts, повторно не опрашиваются.

success = target_node_id in closest_contacts.

# Bootstrap
ping_raw(host, port) — PING по адресу без Contact получателя.

После join: routing.add_or_update + self-lookup.

Ошибка bootstrap не останавливает узел.

После присоединения bootstrap не требуется для дальнейших lookup
