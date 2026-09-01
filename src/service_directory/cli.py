"""Console entrypoint: ``service-directory serve``.

Binds 0.0.0.0:80 by default; host/port configurable via env or flags. If the
bind fails (e.g. :80 in use or requires privileges), prints a clear,
actionable error and exits with a non-zero status instead of crash-looping.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys

from .config import ConfigError

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 80


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="service-directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the dashboard web server")
    serve.add_argument(
        "--host",
        default=os.environ.get("SERVICE_REGISTRY_HOST", DEFAULT_HOST),
        help="Bind host (default: 0.0.0.0, env SERVICE_REGISTRY_HOST)",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SERVICE_REGISTRY_PORT", DEFAULT_PORT)),
        help="Bind port (default: 80, env SERVICE_REGISTRY_PORT)",
    )
    serve.add_argument(
        "--config",
        default=None,
        help="Path to config YAML (default: env SERVICE_REGISTRY_CONFIG)",
    )

    return parser.parse_args(argv)


def _check_bindable(host: str, port: int) -> None:
    """Raise a clear OSError-derived message if (host, port) can't be bound.

    This is a preflight check so the server fails fast with a clear message
    rather than looping / crashing deep inside the ASGI server.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    finally:
        sock.close()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if args.command != "serve":
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 2

    try:
        from .app import create_app_from_env
    except Exception as exc:  # noqa: BLE001 - defensive: import-time failures shouldn't crash-loop
        print(f"Error: failed to initialize application: {exc}", file=sys.stderr)
        return 1

    try:
        app = create_app_from_env(args.config)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        _check_bindable(args.host, args.port)
    except OSError as exc:
        print(
            f"Error: cannot bind {args.host}:{args.port} ({exc}). "
            f"Choose a different port with --port/SERVICE_REGISTRY_PORT, "
            f"or run with sufficient privileges for port {args.port}.",
            file=sys.stderr,
        )
        return 1

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
