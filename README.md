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

## 
Структура репозитория
###
```
p2p-overlay-node/
├── README.md
├── ARCHITECTURE.md
├── PROTOCOL.md
├── LICENSE
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── src/
│   └── p2pnode/
│       ├── __init__.py
│       ├── __main__.py
│       ├── config.py
│       ├── logging_setup.py
│       ├── transport/
│       │   ├── __init__.py
│       │   ├── connection.py
│       │   ├── server.py
│       │   └── framing.py
│       ├── protocol/
│       │   ├── __init__.py
│       │   ├── constants.py
│       │   ├── messages.py
│       │   └── codec.py
│       ├── identity/
│       │   ├── __init__.py
│       │   └── node_id.py
│       ├── rpc/
│       │   ├── __init__.py
│       │   ├── dispatcher.py
│       │   └── handlers.py
│       ├── routing/
│       │   ├── __init__.py
│       │   └── contact.py
│       └── node/
│           ├── __init__.py
│           └── node.py
├── tests/
│   ├── __init__.py
│   ├── test_framing.py
│   ├── test_codec.py
│   ├── test_dispatcher.py
│   └── test_negative.py
├── scripts/
│   ├── run_two_nodes_demo.py
│   ├── demo_frames.py
│   └── demo_negative.py
└── configs/
    ├── node-01.env
    └── node-02.env
```
###

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
