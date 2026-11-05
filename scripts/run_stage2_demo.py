from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import socket
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from p2pnode.config import Config
from p2pnode.logging_setup import setup_logging
from p2pnode.node.node import Node
from p2pnode.protocol.constants import PROTOCOL_VERSION
from p2pnode.routing.contact import xor_distance
from p2pnode.routing.lookup import lookup_node


OUT_ROOT = ROOT / "state" / "stage2"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def clean_dir(p: Path) -> None:
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
    p.mkdir(parents=True, exist_ok=True)


def make_config(
    port: int, state_dir: Path, bootstrap: list[str]
) -> Config:
    return Config(
        node_state_dir=state_dir,
        listen_host="127.0.0.1",
        listen_port=port,
        bootstrap_peers=tuple(bootstrap),
        node_id_bits=256,
        k_bucket_size=3,
        alpha=3,
        connect_timeout_ms=2000,
        read_timeout_ms=3000,
        ping_timeout_ms=3000,
        max_frame_payload=65536,
        protocol_version=PROTOCOL_VERSION,
        log_level="INFO",
    )


def start_node(name: str, port: int, state_dir: Path, bootstrap: list[str]) -> Node:
    state_dir.mkdir(parents=True, exist_ok=True)
    cfg = make_config(port, state_dir, bootstrap)
    node = Node(cfg)
    node.start()
    return node


def dump_routing(node: Node, path: Path) -> None:
    snap = node.routing.snapshot()
    payload = {
        "node_id": node.identity.node_id.hex(),
        "listen": f"{node.config.listen_host}:{node.config.listen_port}",
        "total_contacts": len(node.routing),
        "buckets": snap,
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def run_scheme(scheme: str) -> dict:
    print(f"\n========== scheme={scheme} ==========")
    out_dir = OUT_ROOT / scheme
    clean_dir(out_dir)

    n = 5
    ports = [free_port() for _ in range(n)]
    nodes: list[Node] = []
    bootstrap: list[list[str]] = [[] for _ in range(n)]

    # star: все → seed. ring: i → i-1.
    for i in range(n):
        if i == 0:
            bootstrap[i] = []
        elif scheme == "star":
            bootstrap[i] = [f"127.0.0.1:{ports[0]}"]
        elif scheme == "ring":
            bootstrap[i] = [f"127.0.0.1:{ports[i - 1]}"]
        else:
            raise ValueError(scheme)

    # Запуск узлов.
    for i in range(n):
        name = f"{scheme}-n{i}"
        state = out_dir / name
        node = start_node(
            name, ports[i], state, bootstrap[i] if i > 0 else []
        )
        nodes.append(node)
        print(f"  started {name} port={ports[i]}")

    time.sleep(1.5)  # дать время bootstrap (self-lookup)

    # Присоединяем не-seed узлы.
    for i in range(1, n):
        result = nodes[i].join(bootstrap[i])
        if not result.success:
            print(f"  ERROR: {scheme}-n{i} bootstrap failed")
            for node in nodes:
                node.stop()
            raise RuntimeError(f"bootstrap failed for {scheme}-n{i}")

    time.sleep(2.0)  # сходимость

    # Выгрузка routing.
    for i, node in enumerate(nodes):
        name = f"{scheme}-n{i}"
        path = out_dir / f"routing_{name}.json"
        dump_routing(node, path)
        print(f"  dump routing: {path.name} size={len(node.routing)}")

    # Сводный файл с размерами.
    sizes = [len(node.routing) for node in nodes]
    print(f"  routing sizes: {sizes}")
    if max(sizes) >= n - 1:
        print(
            f"  WARNING: some node knows all {n-1} peers — DHT is degenerate"
        )

    # Поиск 10+ пар (инициатор, цель), где цель НЕ в routing инициатора.
    pairs = []
    for i, ini in enumerate(nodes):
        for j, tgt in enumerate(nodes):
            if i == j:
                continue
            if tgt.identity.node_id not in ini.routing:
                pairs.append((i, j))
    print(f"  candidate pairs (target not in initiator): {len(pairs)}")
    if len(pairs) < 10:
        print(
            f"  WARNING: only {len(pairs)} pairs; network is too small "
            f"or DHT is degenerate"
        )
    pairs = pairs[:10]

    # Lookup.
    results = []
    for k, (i, j) in enumerate(pairs, 1):
        ini = nodes[i]
        tgt = nodes[j]
        target_id = tgt.identity.node_id
        res = lookup_node(ini, target_id)
        rec = {
            "scheme": scheme,
            "lookup_idx": k,
            "initiator": f"{scheme}-n{i}",
            "target": f"{scheme}-n{j}",
            "target_in_initiator_before": False,
            "target_found": res.success,
            "rpc_count": res.rpc_count,
            "iterations": res.iterations,
            "timeouts": len(res.timeouts),
            "duration_ms": res.duration_ms,
            "closest_contacts": ",".join(
                c.node_id.hex()[:8] for c in res.closest_contacts
            ),
        }
        results.append(rec)
        print(
            f"  lookup {k:>2}: {ini.identity.short_id}→{tgt.identity.short_id} "
            f"found={res.success} rpc={res.rpc_count} iters={res.iterations}"
        )

    # CSV с результатами lookup.
    csv_path = out_dir / f"lookups_{scheme}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"  wrote {csv_path}")

    # Остановка bootstrap (seed n0).
    print(f"  stopping seed {scheme}-n0 (bootstrap)")
    nodes[0].stop()
    time.sleep(0.5)

    # После остановки bootstrap: lookup между двумя ранее присоединившимися.
    # Возьмём n1 → n3.
    tgt_id = nodes[3].identity.node_id
    # Цель n3 могла быть в routing n1? Проверим.
    before = tgt_id in nodes[1].routing
    post = lookup_node(nodes[1], tgt_id)
    print(
        f"  post-bootstrap lookup n1→n3: target_before={before} "
        f"found={post.success} rpc={post.rpc_count}"
    )

    # Остановка остальных.
    for i in range(1, n):
        nodes[i].stop()

    return {
        "scheme": scheme,
        "n": n,
        "k": nodes[0].config.k_bucket_size,
        "routing_sizes": sizes,
        "candidate_pairs": len(pairs),
        "lookups": results,
        "post_bootstrap_lookup_found": post.success,
        "post_bootstrap_target_before": before,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scheme",
        choices=["star", "ring", "both"],
        default="both",
    )
    args = parser.parse_args()

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    setup_logging("INFO", OUT_ROOT / "logs")

    schemes = ["star", "ring"] if args.scheme == "both" else [args.scheme]
    summaries = []
    for scheme in schemes:
        summaries.append(run_scheme(scheme))

    # Сводный JSON.
    summary_path = OUT_ROOT / "summary.json"
    summary_path.write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSummary written to {summary_path}")

    # Итоговая проверка.
    all_ok = True
    for s in summaries:
        scheme = s["scheme"]
        n = s["n"]
        sizes = s["routing_sizes"]
        # Не менее 80% узлов имеют < N-1 контактов
        less_than_all = sum(1 for x in sizes if x < n - 1)
        if less_than_all < 0.8 * n:
            print(f"  WARNING [{scheme}]: {less_than_all}/{n} < N-1 contacts")
            all_ok = False
        # Хотя бы 10 lookups
        if len(s["lookups"]) < 10:
            print(f"  WARNING [{scheme}]: only {len(s['lookups'])} lookups")
        # Успешных lookup >= 80%
        found = sum(1 for l in s["lookups"] if l["target_found"])
        if found < 0.8 * len(s["lookups"]):
            print(f"  WARNING [{scheme}]: only {found} lookups succeeded")
            all_ok = False
        # Post-bootstrap lookup работает
        if not s["post_bootstrap_lookup_found"]:
            print(f"  WARNING [{scheme}]: post-bootstrap lookup failed")
            all_ok = False

    if all_ok:
        print("\n=== STAGE 2 DEMO PASSED ===")
        return 0
    else:
        print("\n=== STAGE 2 DEMO COMPLETED WITH WARNINGS ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())