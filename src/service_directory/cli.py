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

from .config import ConfigError, load_config, resolve_state_dir

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

    token = subparsers.add_parser("token", help="Manage pairing tokens")
    token_sub = token.add_subparsers(dest="token_command", required=True)
    token_issue = token_sub.add_parser(
        "issue", help="Mint a short-lived one-time pairing code for this node"
    )
    token_issue.add_argument(
        "--url",
        default=None,
        help="Base URL of the running local node (default: http://127.0.0.1:<port>)",
    )
    token_issue.add_argument("--port", type=int, default=DEFAULT_PORT)
    token_issue.add_argument("--config", default=None)

    pair = subparsers.add_parser(
        "pair", help="Pair with a remote peer node using a pairing code"
    )
    pair.add_argument("--url", required=True, help="Base URL of the peer to pair with")
    pair.add_argument("--code", required=True, help="Pairing code issued by the peer")
    pair.add_argument("--config", default=None)

    peers = subparsers.add_parser("peers", help="Manage trusted peers")
    peers_sub = peers.add_subparsers(dest="peers_command", required=True)
    peers_sub.add_parser("list", help="List trusted peers")
    peers_remove = peers_sub.add_parser("remove", help="Remove a trusted peer")
    peers_remove.add_argument("name", help="Name of the peer to remove")
    peers.add_argument("--config", default=None)

    doctor = subparsers.add_parser(
        "doctor",
        help="Run a diagnostic checklist (config, identity, peers, install, service)",
    )
    doctor.add_argument("--config", default=None)
    doctor.add_argument(
        "--host",
        default=os.environ.get("SERVICE_REGISTRY_HOST", DEFAULT_HOST),
        help="Host to check bind-availability for (default: 0.0.0.0)",
    )
    doctor.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SERVICE_REGISTRY_PORT", DEFAULT_PORT)),
        help="Port to check bind-availability for (default: 80)",
    )
    doctor.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color in the checklist output",
    )

    service = subparsers.add_parser(
        "service", help="Manage the systemd --user unit / launchd agent"
    )
    service_sub = service.add_subparsers(dest="service_command", required=True)
    for sub_name, sub_help in [
        ("install", "Install and start the service (systemd --user / launchd)"),
        ("uninstall", "Stop and remove the service unit/agent"),
        ("start", "Start the service"),
        ("stop", "Stop the service"),
        ("status", "Show service status"),
        ("logs", "Show recent service logs"),
    ]:
        service_sub.add_parser(sub_name, help=sub_help)

    subparsers.add_parser(
        "upgrade",
        help="Stop, reinstall (uv tool), regenerate the unit, restart, and verify",
    )

    return parser.parse_args(argv)


def _local_context(config_path: str | None):
    """Load config + derive the federation identity bits the pairing/peers
    commands need (name, state dir, device identity)."""
    from .app import _local_name
    from .identity import load_or_create_identity

    config = load_config(config_path)
    state_dir = resolve_state_dir(config)
    identity = load_or_create_identity(state_dir)
    name = _local_name(config)
    return config, state_dir, identity, name


def cmd_token_issue(args: argparse.Namespace) -> int:
    """Mint a short-lived one-time pairing code by calling the running local
    node's admin endpoint (relies on the localhost socket-IP bypass)."""
    import httpx2 as httpx

    base_url = args.url or f"http://127.0.0.1:{args.port}"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(f"{base_url.rstrip('/')}/api/federation/pairing-code")
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 - CLI must report, never stack-trace
        print(
            f"Error: could not reach local node at {base_url} ({exc}). "
            f"Is `service-directory serve` running?",
            file=sys.stderr,
        )
        return 1

    print(data["code"])
    return 0


def cmd_pair(args: argparse.Namespace) -> int:
    """Pair with a remote peer: present the code + our identity, receive the
    peer's identity + a per-peer token, and record it in our trust store."""
    import httpx2 as httpx

    from .trust_store import PeerRecord, upsert_peer

    try:
        config, state_dir, identity, name = _local_context(args.config)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    payload = {
        "device_id": identity.device_id,
        "name": name,
        "base_url": config.federation.base_url,
        "code": args.code,
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{args.url.rstrip('/')}/api/federation/pair", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 - CLI must report, never stack-trace
        print(f"Error: pairing with {args.url} failed ({exc})", file=sys.stderr)
        return 1

    upsert_peer(
        state_dir,
        PeerRecord(
            name=data["name"],
            device_id=data["device_id"],
            base_url=data["base_url"],
            token=data["token"],
        ),
    )
    print(f"Paired with '{data['name']}' ({args.url})")
    return 0


def cmd_peers_list(args: argparse.Namespace) -> int:
    from .trust_store import load_peers

    try:
        _config, state_dir, _identity, _name = _local_context(args.config)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    peers = load_peers(state_dir)
    if not peers:
        print("No trusted peers.")
        return 0
    for peer in peers:
        print(f"{peer.name}\t{peer.base_url}\t{peer.device_id}")
    return 0


def cmd_peers_remove(args: argparse.Namespace) -> int:
    from .trust_store import remove_peer

    try:
        _config, state_dir, _identity, _name = _local_context(args.config)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if remove_peer(state_dir, args.name):
        print(f"Removed peer '{args.name}'.")
        return 0
    print(f"Error: no trusted peer named '{args.name}'", file=sys.stderr)
    return 1


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run the diagnostic checklist and print it; exit non-zero on any
    "fail" status (warnings don't fail the exit code -- they're advisory).
    """
    from .doctor import DoctorDependencies, run_and_format

    deps = DoctorDependencies(config_path=args.config, host=args.host, port=args.port)
    text, all_ok = run_and_format(deps, color=not args.no_color)
    print(text)
    return 0 if all_ok else 1


def cmd_service(args: argparse.Namespace) -> int:
    """Dispatch to the systemd --user / launchd service manager."""
    from .service_manager import UnsupportedPlatformError, get_service_manager

    try:
        manager = get_service_manager()
    except UnsupportedPlatformError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    action = {
        "install": manager.install,
        "uninstall": manager.uninstall,
        "start": manager.start,
        "stop": manager.stop,
        "status": manager.status,
        "logs": manager.logs,
    }.get(args.service_command)
    if action is None:  # pragma: no cover - defensive; argparse restricts choices
        print(f"Unknown service command: {args.service_command}", file=sys.stderr)
        return 2

    result = action()
    if result.output:
        print(result.output)
    print(result.message)
    return 0 if result.ok else 1


def cmd_upgrade(args: argparse.Namespace) -> int:
    """Stop -> reinstall (uv tool) -> regenerate unit -> restart -> verify."""
    from .upgrade import run_upgrade

    result = run_upgrade()
    print(result.message)
    if result.skipped:
        return 0
    return 0 if result.ok else 1


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

    if args.command == "token" and args.token_command == "issue":
        return cmd_token_issue(args)
    if args.command == "pair":
        return cmd_pair(args)
    if args.command == "peers" and args.peers_command == "list":
        return cmd_peers_list(args)
    if args.command == "peers" and args.peers_command == "remove":
        return cmd_peers_remove(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "service":
        return cmd_service(args)
    if args.command == "upgrade":
        return cmd_upgrade(args)

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
