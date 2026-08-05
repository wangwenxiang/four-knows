#!/usr/bin/env python3
"""Serve poster HTML on a collision-free local HTTP port for Browser capture."""

from __future__ import annotations

import argparse
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def create_server(project: Path, host: str, port: int) -> ThreadingHTTPServer:
    project = project.resolve()
    if not project.is_dir():
        raise RuntimeError(f"Project directory does not exist: {project}")
    handler = functools.partial(QuietHandler, directory=str(project))
    return ThreadingHTTPServer((host, port), handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 asks the OS for a free port")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = create_server(args.project, args.host, args.port)
    actual_host, actual_port = server.server_address[:2]
    print(
        json.dumps(
            {
                "host": actual_host,
                "port": actual_port,
                "baseUrl": f"http://{actual_host}:{actual_port}",
                "project": str(args.project.resolve()),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
