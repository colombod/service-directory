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

from . import __version__
from .config import ConfigError, load_config, resolve_state_dir

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 80


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="service-directory")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Print the installed version and exit",
    )
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

    token_issue_write = token_sub.add_parser(
        "issue-write",
        help=(
            "Mint (and persist, rotating any existing one) a write token "
            "that authorizes registry mutations (register/deregister/"
            "heartbeat). Localhost/admin only -- mints directly against the "
            "state dir, no running server required."
        ),
    )
    token_issue_write.add_argument("--config", default=None)

    register = subparsers.add_parser(
        "register", help="Register (or update) a dynamic service with the local node"
    )
    register.add_argument("--name", required=True, help="Service name")
    register.add_argument("--port", type=int, default=None, help="Service port")
    register.add_argument(
        "--url", default=None, help="Service URL (alternative to --port)"
    )
    register.add_argument("--path", default=None, help="URL path (default '/')")
    register.add_argument("--description", default=None)
    register.add_argument("--category", default=None)
    register.add_argument("--health-url", default=None, help="HTTP health-check URL")
    register.add_argument(
        "--ttl",
        type=float,
        default=None,
        help="Heartbeat TTL in seconds (default: persistent)",
    )
    register.add_argument(
        "--url-base",
        default=None,
        help="Base URL of the running local node (default: http://127.0.0.1:<port>)",
    )
    register.add_argument(
        "--port-server", type=int, default=DEFAULT_PORT, dest="server_port"
    )
    register.add_argument(
        "--token", default=None, help="Write token (default: localhost bypass)"
    )
    register.add_argument("--config", default=None)

    deregister = subparsers.add_parser(
        "deregister", help="Deregister a dynamic service from the local node"
    )
    deregister.add_argument("name", help="Name of the service to deregister")
    deregister.add_argument("--url-base", default=None)
    deregister.add_argument(
        "--port-server", type=int, default=DEFAULT_PORT, dest="server_port"
    )
    deregister.add_argument("--token", default=None)
    deregister.add_argument("--config", default=None)

    heartbeat = subparsers.add_parser(
        "heartbeat", help="Send a liveness heartbeat for a ttl dynamic service"
    )
    heartbeat.add_argument("name", help="Name of the service to heartbeat")
    heartbeat.add_argument("--url-base", default=None)
    heartbeat.add_argument(
        "--port-server", type=int, default=DEFAULT_PORT, dest="server_port"
    )
    heartbeat.add_argument("--token", default=None)
    heartbeat.add_argument("--config", default=None)

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
        ("uninstall", "Stop and remove the service unit/agent"),
        ("start", "Start the service"),
        ("stop", "Stop the service"),
        ("status", "Show service status"),
        ("logs", "Show recent service logs"),
    ]:
        service_sub.add_parser(sub_name, help=sub_help)

    service_install = service_sub.add_parser(
        "install", help="Install and start the service (systemd --user / launchd)"
    )
    service_install.add_argument(
        "--config",
        default=None,
        help=(
            "Path to config YAML to bake into the installed unit "
            "(default: env SERVICE_REGISTRY_CONFIG)"
        ),
    )
    service_install.add_argument(
        "--host",
        default=None,
        help=(
            "Bind host to bake into the installed unit "
            "(default: env SERVICE_REGISTRY_HOST, then 0.0.0.0)"
        ),
    )
    service_install.add_argument(
        "--port",
        type=int,
        default=None,
        help=(
            "Bind port to bake into the installed unit "
            "(default: env SERVICE_REGISTRY_PORT, then 80)"
        ),
    )

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


def cmd_token_issue_write(args: argparse.Namespace) -> int:
    """Mint (and persist, rotating any existing one) the write token that
    authorizes registry mutations. Localhost/admin only -- this mints
    directly against the state dir (no running server required), matching
    how ``write_token.py`` is meant to be operated.
    """
    from .write_token import issue_write_token

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    state_dir = resolve_state_dir(config)
    token = issue_write_token(state_dir)
    print(token)
    return 0


def _write_token_header(state_dir: str, explicit_token: str | None) -> dict[str, str]:
    """Best-effort Authorization header for registry-mutation CLI commands:
    an explicit ``--token`` wins; otherwise fall back to the token
    persisted in the state dir (if any); otherwise no header at all,
    relying on the localhost socket-IP bypass.
    """
    from .write_token import load_write_token

    token = explicit_token or load_write_token(state_dir)
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def cmd_register(args: argparse.Namespace) -> int:
    """Register/update a dynamic service by calling the running local
    node's ``POST /api/services`` endpoint."""
    import httpx2 as httpx

    try:
        _config, state_dir, _identity, _name = _local_context(args.config)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    base_url = args.url_base or f"http://127.0.0.1:{args.server_port}"
    payload = {
        "name": args.name,
        "port": args.port,
        "url": args.url,
        "path": args.path,
        "description": args.description,
        "category": args.category,
        "health_url": args.health_url,
        "ttl": args.ttl,
    }
    headers = _write_token_header(state_dir, args.token)
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{base_url.rstrip('/')}/api/services", json=payload, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 - CLI must report, never stack-trace
        print(f"Error: registration failed ({exc})", file=sys.stderr)
        return 1

    print(f"Registered '{data['name']}'.")
    return 0


def cmd_deregister(args: argparse.Namespace) -> int:
    """Deregister a dynamic service via ``DELETE /api/services/{name}``."""
    import httpx2 as httpx

    try:
        _config, state_dir, _identity, _name = _local_context(args.config)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    base_url = args.url_base or f"http://127.0.0.1:{args.server_port}"
    headers = _write_token_header(state_dir, args.token)
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.delete(
                f"{base_url.rstrip('/')}/api/services/{args.name}", headers=headers
            )
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - CLI must report, never stack-trace
        print(f"Error: deregistration failed ({exc})", file=sys.stderr)
        return 1

    print(f"Deregistered '{args.name}'.")
    return 0


def cmd_heartbeat(args: argparse.Namespace) -> int:
    """Send a liveness heartbeat via
    ``POST /api/services/{name}/heartbeat``."""
    import httpx2 as httpx

    try:
        _config, state_dir, _identity, _name = _local_context(args.config)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    base_url = args.url_base or f"http://127.0.0.1:{args.server_port}"
    headers = _write_token_header(state_dir, args.token)
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{base_url.rstrip('/')}/api/services/{args.name}/heartbeat",
                headers=headers,
            )
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - CLI must report, never stack-trace
        print(f"Error: heartbeat failed ({exc})", file=sys.stderr)
        return 1

    print(f"Heartbeat sent for '{args.name}'.")
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
    from .service_manager import (
        InvalidInstallValueError,
        UnsupportedPlatformError,
        get_service_manager,
    )

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

    if args.service_command == "install":
        try:
            result = manager.install(config=args.config, host=args.host, port=args.port)
        except InvalidInstallValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
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
    if args.command == "token" and args.token_command == "issue-write":
        return cmd_token_issue_write(args)
    if args.command == "register":
        return cmd_register(args)
    if args.command == "deregister":
        return cmd_deregister(args)
    if args.command == "heartbeat":
        return cmd_heartbeat(args)
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
