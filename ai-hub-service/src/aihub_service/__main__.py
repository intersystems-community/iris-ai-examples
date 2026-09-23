"""``python -m aihub_service --config examples/careconnect/offline.yaml``"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="aihub_service")
    parser.add_argument("--config", default=os.environ.get("AIHUB_CONFIG", "/etc/aihub/service.yaml"))
    parser.add_argument("--host", default=os.environ.get("AIHUB_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("AIHUB_PORT", "8080")))
    args = parser.parse_args()

    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(args.config), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
