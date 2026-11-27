"""CLI (run from backend/):  python -m agents.policy_mapping <ingest|map-pending|map-doc CODE|map-ids 1 2|worker|impact CODE|serve>"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from .service import Agent3Service


def main() -> None:
    p = argparse.ArgumentParser(prog="agents.policy_mapping")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest")
    mp = sub.add_parser("map-pending")
    mp.add_argument("--limit", type=int)
    md = sub.add_parser("map-doc")
    md.add_argument("doc_code")
    mi = sub.add_parser("map-ids")
    mi.add_argument("ids", nargs="+", type=int)
    im = sub.add_parser("impact")
    im.add_argument("doc_code")
    w = sub.add_parser("worker")
    w.add_argument("--interval", type=int, default=20)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8003)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if sys.platform == "win32":  # psycopg async needs the selector loop on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    if args.cmd == "serve":
        from run import serve

        serve(port=args.port)
        return

    svc = Agent3Service()
    coro = {
        "ingest": lambda: svc.ingest(),
        "map-pending": lambda: svc.map_pending(args.limit),
        "map-doc": lambda: svc.map_document(args.doc_code),
        "map-ids": lambda: svc.map_obligations(args.ids),
        "impact": lambda: svc.impact(args.doc_code),
        "worker": lambda: svc.worker(args.interval),
    }[args.cmd]()
    print(json.dumps(asyncio.run(coro), indent=2, default=str))


if __name__ == "__main__":
    main()
